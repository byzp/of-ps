#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>

#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <mutex>
#include <vector>
#include <chrono>
#include <atomic>
#include <new>

#ifdef _WIN32
#include <windows.h>
#else
#include <sys/time.h>
#include <unistd.h>
#endif

extern "C" {
#include "ikcp.h"
}

/*
 * KCP Protocol Python Extension
 * 
 * Thread-safe implementation supporting Python 3.13+ free-threading.
 * 
 * Deadlock Prevention Strategy:
 * 1. Never hold mutex while calling Python callbacks
 * 2. Use output queue pattern - collect output during KCP operations,
 *    release lock, then process queue with Python calls
 * 3. Fine-grained locking with std::lock_guard for exception safety
 * 4. Atomic operations for simple flags accessed from multiple threads
 */


static constexpr int KCP_OVERHEAD = 24;
static constexpr uint32_t DEAD_TIMEOUT_MS = 10000;
static constexpr int KCP_NODELAY = 1;        // Enable nodelay mode
static constexpr int KCP_INTERVAL = 10;      // Internal update interval (ms)
static constexpr int KCP_RESEND = 2;         // Fast resend trigger count
static constexpr int KCP_NC = 1;             // Disable congestion control
static constexpr int KCP_SNDWND = 128;       // Send window size
static constexpr int KCP_RCVWND = 128;       // Receive window size
static constexpr int KCP_MTU = 1400;         // Maximum transmission unit


/*
 * Get current time in milliseconds using steady clock.
 * This is thread-safe and monotonic.
 */
static inline uint32_t current_ms_impl() noexcept {
    using namespace std::chrono;
    auto now = steady_clock::now();
    auto ms = duration_cast<milliseconds>(now.time_since_epoch()).count();
    return static_cast<uint32_t>(ms & 0xFFFFFFFF);
}

/*
 * Output Queue Item
 * 
 * Used to defer Python callback invocation until after mutex is released.
 * This is critical for deadlock prevention.
 */

struct OutputItem {
    std::vector<char> data;
    
    OutputItem(const char* buf, int len) : data(buf, buf + len) {}
    
    // Move semantics for efficiency
    OutputItem(OutputItem&&) noexcept = default;
    OutputItem& operator=(OutputItem&&) noexcept = default;
    
    // Disable copy to prevent accidental copies
    OutputItem(const OutputItem&) = delete;
    OutputItem& operator=(const OutputItem&) = delete;
};

/*
 * KCPSession Object Structure
 * 
 * Note: C++ objects use pointers because tp_alloc provides zero-initialized
 * memory without calling constructors. We manually manage construction.
 */

struct KCPSessionObject {
    PyObject_HEAD
    
    // KCP control block (from ikcp.c)
    ikcpcb* kcp;
    
    // Python callback for sending UDP packets
    PyObject* output_callback;
    
    // Mutex for thread-safe access to KCP state
    // Using pointer because PyObject memory is zero-initialized, not constructed
    std::mutex* mtx;
    
    // Queue for deferred output - populated during KCP operations,
    // processed after releasing mutex
    std::vector<OutputItem>* output_queue;
    
    // Atomic flag for dead session (can be read without lock)
    std::atomic<int> dead;
    
    // Last time we received data (for timeout detection)
    uint32_t last_recv_time;
    
    // Conversation ID (immutable after init)
    uint32_t conv;
};

// Forward declaration
//static PyTypeObject KCPSessionType;

/*
 * KCP Output Callback
 * 
 * IMPORTANT: This is called from within ikcp_update/ikcp_flush while
 * our mutex is held. We MUST NOT call Python code here.
 * Instead, we queue the data for later processing.
 */

static int kcp_output_callback(const char* buf, int len, ikcpcb* kcp, void* user) {
    KCPSessionObject* self = static_cast<KCPSessionObject*>(user);
    
    // Mutex is already held by the caller (ikcp_update, etc.)
    // Just queue the data - do NOT call Python here!
    try {
        self->output_queue->emplace_back(buf, len);
        return 0;
    } catch (const std::bad_alloc&) {
        return -1;
    }
}

/*
 * Output Queue Processing
 * 
 * CRITICAL: This function must be called WITHOUT the mutex held.
 * It takes ownership of queued items and calls the Python callback.
 * 
 * Deadlock Prevention:
 * 1. Atomically swap the queue under mutex
 * 2. Release mutex
 * 3. Process items and call Python callbacks
 * 4. If callback tries to use this session, it will acquire mutex normally
 */

static void process_output_queue(KCPSessionObject* self) {
    std::vector<OutputItem> local_queue;
    PyObject* callback = nullptr;
    
    // Phase 1: Atomically take the queue and get callback reference
    // This is a very short critical section
    {
        std::lock_guard<std::mutex> guard(*self->mtx);
        
        // Swap queues - local_queue gets all pending items, output_queue becomes empty
        local_queue.swap(*self->output_queue);
        
        // Get callback reference (INCREF while holding lock for safety)
        callback = self->output_callback;
        Py_XINCREF(callback);
    }
    // Mutex is now released!
    
    // Phase 2: Process queue without holding any locks
    if (callback == nullptr || local_queue.empty()) {
        Py_XDECREF(callback);
        return;
    }
    
    for (auto& item : local_queue) {
        // Create Python bytes object from queued data
        PyObject* data = PyBytes_FromStringAndSize(
            item.data.data(), 
            static_cast<Py_ssize_t>(item.data.size())
        );
        
        if (data != nullptr) {
            // Call the Python callback - this may trigger arbitrary Python code
            // including re-entering this KCPSession (which is safe, no deadlock)
            PyObject* result = PyObject_CallOneArg(callback, data);
            
            // Handle callback errors silently (best-effort output)
            Py_XDECREF(result);
            if (PyErr_Occurred()) {
                // Clear error - we don't want callback errors to propagate
                // The caller can check their own error handling
                PyErr_Clear();
            }
            
            Py_DECREF(data);
        } else {
            // Memory allocation failed, clear error and continue
            PyErr_Clear();
        }
    }
    
    Py_DECREF(callback);
}


/**
 * Allocate new KCPSession object.
 * Just allocates memory and initializes to safe defaults.
 */
static PyObject* KCPSession_new(PyTypeObject* type, PyObject* args, PyObject* kwds) {
    KCPSessionObject* self = reinterpret_cast<KCPSessionObject*>(
        type->tp_alloc(type, 0)
    );
    
    if (self != nullptr) {
        self->kcp = nullptr;
        self->output_callback = nullptr;
        self->mtx = nullptr;
        self->output_queue = nullptr;
        self->dead.store(0, std::memory_order_relaxed);
        self->last_recv_time = 0;
        self->conv = 0;
    }
    
    return reinterpret_cast<PyObject*>(self);
}

/**
 * Initialize KCPSession with conversation ID and output callback.
 * 
 * Args:
 *     conv: Conversation ID (uint32)
 *     output: Callable that takes bytes and sends as UDP packet
 */
static int KCPSession_init(KCPSessionObject* self, PyObject* args, PyObject* kwds) {
    static const char* kwlist[] = {"conv", "output", nullptr};
    unsigned int conv;
    PyObject* output_callback;
    
    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "IO", 
            const_cast<char**>(kwlist), 
            &conv, &output_callback)) {
        return -1;
    }
    
    // Validate callback
    if (!PyCallable_Check(output_callback)) {
        PyErr_SetString(PyExc_TypeError, "output must be callable");
        return -1;
    }
    
    // Allocate C++ objects
    try {
        self->mtx = new std::mutex();
        self->output_queue = new std::vector<OutputItem>();
        self->output_queue->reserve(16);  // Pre-allocate for typical usage
    } catch (const std::bad_alloc&) {
        delete self->mtx;
        self->mtx = nullptr;
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate session structures");
        return -1;
    }
    
    // Create KCP control block
    self->kcp = ikcp_create(conv, self);
    if (self->kcp == nullptr) {
        delete self->output_queue;
        delete self->mtx;
        self->output_queue = nullptr;
        self->mtx = nullptr;
        PyErr_SetString(PyExc_MemoryError, "Failed to create KCP control block");
        return -1;
    }
    
    // Store callback with reference
    Py_INCREF(output_callback);
    self->output_callback = output_callback;
    
    // Store immutable fields
    self->conv = conv;
    self->last_recv_time = current_ms_impl();
    
    // Set KCP output callback
    ikcp_setoutput(self->kcp, kcp_output_callback);
    
    // Configure KCP with hardcoded parameters
    // These settings optimize for low latency
    ikcp_nodelay(self->kcp, KCP_NODELAY, KCP_INTERVAL, KCP_RESEND, KCP_NC);
    ikcp_wndsize(self->kcp, KCP_SNDWND, KCP_RCVWND);
    ikcp_setmtu(self->kcp, KCP_MTU);
    
    return 0;
}

/**
 * Deallocate KCPSession.
 * Clean up all resources in reverse order of allocation.
 */
static void KCPSession_dealloc(KCPSessionObject* self) {
    // Release KCP control block
    if (self->kcp != nullptr) {
        ikcp_release(self->kcp);
        self->kcp = nullptr;
    }
    
    // Release Python callback reference
    Py_XDECREF(self->output_callback);
    self->output_callback = nullptr;
    
    // Delete C++ objects
    delete self->output_queue;
    self->output_queue = nullptr;
    
    delete self->mtx;
    self->mtx = nullptr;
    
    // Free Python object
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject*>(self));
}

/**
 * Feed received UDP data into KCP.
 * 
 * Args:
 *     data: Bytes received from UDP socket
 */
static PyObject* KCPSession_input(KCPSessionObject* self, PyObject* args) {
    Py_buffer buffer;
    
    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        return nullptr;
    }
    
    // Process input under mutex
    {
        std::lock_guard<std::mutex> guard(*self->mtx);
        
        if (self->kcp != nullptr) {
            int ret = ikcp_input(
                self->kcp,
                static_cast<const char*>(buffer.buf),
                static_cast<long>(buffer.len)
            );
            
            // Update last receive time on successful input
            if (ret >= 0) {
                self->last_recv_time = current_ms_impl();
            }
        }
    }
    // Mutex released here
    
    PyBuffer_Release(&buffer);
    
    // Process any queued output (without mutex)
    process_output_queue(self);
    
    Py_RETURN_NONE;
}

/**
 * Receive decoded message from KCP.
 * 
 * Returns:
 *     bytes: Decoded message, or None if no complete message available
 */
static PyObject* KCPSession_recv(KCPSessionObject* self, PyObject* Py_UNUSED(ignored)) {
    std::vector<char> buffer;
    int recv_size = 0;
    
    // Check and receive under mutex
    {
        std::lock_guard<std::mutex> guard(*self->mtx);
        
        if (self->kcp != nullptr) {
            // Peek to get message size
            int size = ikcp_peeksize(self->kcp);
            
            if (size > 0) {
                buffer.resize(static_cast<size_t>(size));
                recv_size = ikcp_recv(self->kcp, buffer.data(), size);
            }
        }
    }
    // Mutex released here
    
    // Create Python object outside mutex
    if (recv_size > 0) {
        return PyBytes_FromStringAndSize(buffer.data(), recv_size);
    }
    
    Py_RETURN_NONE;
}

/**
 * Send data through KCP.
 * Data will be fragmented and queued for transmission.
 * 
 * Args:
 *     data: Bytes to send
 */
static PyObject* KCPSession_send(KCPSessionObject* self, PyObject* args) {
    Py_buffer buffer;
    
    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        return nullptr;
    }
    
    // Send under mutex
    {
        std::lock_guard<std::mutex> guard(*self->mtx);
        
        if (self->kcp != nullptr) {
            ikcp_send(
                self->kcp,
                static_cast<const char*>(buffer.buf),
                static_cast<int>(buffer.len)
            );
        }
    }
    // Mutex released here
    
    PyBuffer_Release(&buffer);
    
    // Process any queued output (without mutex)
    process_output_queue(self);
    
    Py_RETURN_NONE;
}

/**
 * Update KCP state.
 * Should be called periodically (e.g., every 10-100ms).
 * This triggers retransmissions and sends queued data.
 */
static PyObject* KCPSession_update(KCPSessionObject* self, PyObject* Py_UNUSED(ignored)) {
    uint32_t current = current_ms_impl();
    
    // Update under mutex
    {
        std::lock_guard<std::mutex> guard(*self->mtx);
        
        if (self->kcp != nullptr) {
            // Perform KCP update - this may queue output
            ikcp_update(self->kcp, current);
            
            // Check for timeout
            uint32_t elapsed = current - self->last_recv_time;
            if (elapsed > DEAD_TIMEOUT_MS) {
                self->dead.store(1, std::memory_order_release);
            }
        }
    }
    // Mutex released here
    
    // Process any queued output (without mutex)
    process_output_queue(self);
    
    Py_RETURN_NONE;
}

/**
 * Get dead property.
 * Returns True if session has timed out.
 */
static PyObject* KCPSession_get_dead(KCPSessionObject* self, void* Py_UNUSED(closure)) {
    // Atomic load, no mutex needed
    int dead = self->dead.load(std::memory_order_acquire);
    return PyBool_FromLong(dead);
}

/**
 * Get conv property.
 * Returns the conversation ID.
 */
static PyObject* KCPSession_get_conv(KCPSessionObject* self, void* Py_UNUSED(closure)) {
    // conv is immutable after init, no mutex needed
    return PyLong_FromUnsignedLong(self->conv);
}

static PyMethodDef KCPSession_methods[] = {
    {
        "input",
        reinterpret_cast<PyCFunction>(KCPSession_input),
        METH_VARARGS,
        "input(data)\n\n"
        "Feed UDP packet data into KCP for processing.\n\n"
        "Args:\n"
        "    data: Bytes received from UDP socket"
    },
    {
        "recv",
        reinterpret_cast<PyCFunction>(KCPSession_recv),
        METH_NOARGS,
        "recv() -> bytes | None\n\n"
        "Receive decoded message from KCP.\n\n"
        "Returns:\n"
        "    Decoded message bytes, or None if no complete message available"
    },
    {
        "send",
        reinterpret_cast<PyCFunction>(KCPSession_send),
        METH_VARARGS,
        "send(data)\n\n"
        "Send data through KCP. Data will be fragmented if needed.\n\n"
        "Args:\n"
        "    data: Bytes to send"
    },
    {
        "update",
        reinterpret_cast<PyCFunction>(KCPSession_update),
        METH_NOARGS,
        "update()\n\n"
        "Update KCP state. Should be called periodically (every 10-100ms).\n"
        "This triggers retransmissions and sends queued data."
    },
    {nullptr, nullptr, 0, nullptr}
};

static PyGetSetDef KCPSession_getset[] = {
    {
        "dead",
        reinterpret_cast<getter>(KCPSession_get_dead),
        nullptr,
        "True if session has timed out (no data received for 30 seconds)",
        nullptr
    },
    {
        "conv",
        reinterpret_cast<getter>(KCPSession_get_conv),
        nullptr,
        "Conversation ID (uint32)",
        nullptr
    },
    {nullptr, nullptr, nullptr, nullptr, nullptr}
};

static PyTypeObject KCPSessionType = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    /* tp_name */           "_kcp.KCPSession",
    /* tp_basicsize */      sizeof(KCPSessionObject),
    /* tp_itemsize */       0,
    /* tp_dealloc */        reinterpret_cast<destructor>(KCPSession_dealloc),
    /* tp_vectorcall_offset */ 0,
    /* tp_getattr */        nullptr,
    /* tp_setattr */        nullptr,
    /* tp_as_async */       nullptr,
    /* tp_repr */           nullptr,
    /* tp_as_number */      nullptr,
    /* tp_as_sequence */    nullptr,
    /* tp_as_mapping */     nullptr,
    /* tp_hash */           nullptr,
    /* tp_call */           nullptr,
    /* tp_str */            nullptr,
    /* tp_getattro */       nullptr,
    /* tp_setattro */       nullptr,
    /* tp_as_buffer */      nullptr,
    /* tp_flags */          Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    /* tp_doc */            "KCPSession(conv, output)\n\n"
                            "KCP session for reliable UDP transport.\n\n"
                            "Args:\n"
                            "    conv: Conversation ID (uint32)\n"
                            "    output: Callable that takes bytes and sends via UDP\n\n"
                            "Thread-safe: All methods can be called from multiple threads.",
    /* tp_traverse */       nullptr,
    /* tp_clear */          nullptr,
    /* tp_richcompare */    nullptr,
    /* tp_weaklistoffset */ 0,
    /* tp_iter */           nullptr,
    /* tp_iternext */       nullptr,
    /* tp_methods */        KCPSession_methods,
    /* tp_members */        nullptr,
    /* tp_getset */         KCPSession_getset,
    /* tp_base */           nullptr,
    /* tp_dict */           nullptr,
    /* tp_descr_get */      nullptr,
    /* tp_descr_set */      nullptr,
    /* tp_dictoffset */     0,
    /* tp_init */           reinterpret_cast<initproc>(KCPSession_init),
    /* tp_alloc */          nullptr,
    /* tp_new */            KCPSession_new,
};

/**
 * Extract conversation ID from KCP packet.
 * 
 * Args:
 *     data: Raw KCP packet bytes
 *     
 * Returns:
 *     Conversation ID (uint32)
 *     
 * Raises:
 *     ValueError: If data is too short
 */
static PyObject* py_get_conv(PyObject* Py_UNUSED(module), PyObject* args) {
    Py_buffer buffer;
    
    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        return nullptr;
    }
    
    if (buffer.len < 4) {
        PyBuffer_Release(&buffer);
        PyErr_SetString(PyExc_ValueError, 
            "Data too short to contain conversation ID (need at least 4 bytes)");
        return nullptr;
    }
    
    // KCP conv is first 4 bytes, little-endian
    const auto* p = static_cast<const unsigned char*>(buffer.buf);
    uint32_t conv = static_cast<uint32_t>(p[0]) |
                   (static_cast<uint32_t>(p[1]) << 8) |
                   (static_cast<uint32_t>(p[2]) << 16) |
                   (static_cast<uint32_t>(p[3]) << 24);
    
    PyBuffer_Release(&buffer);
    
    return PyLong_FromUnsignedLong(conv);
}

/**
 * Get current time in milliseconds.
 * Uses monotonic steady clock.
 * 
 * Returns:
 *     Current time in milliseconds (uint32, wraps around)
 */
static PyObject* py_current_ms(PyObject* Py_UNUSED(module), PyObject* Py_UNUSED(ignored)) {
    return PyLong_FromUnsignedLong(current_ms_impl());
}

static PyMethodDef module_methods[] = {
    {
        "get_conv",
        py_get_conv,
        METH_VARARGS,
        "get_conv(data) -> int\n\n"
        "Extract conversation ID from KCP packet.\n\n"
        "Args:\n"
        "    data: Raw KCP packet bytes\n\n"
        "Returns:\n"
        "    Conversation ID as unsigned 32-bit integer\n\n"
        "Raises:\n"
        "    ValueError: If data is shorter than 4 bytes"
    },
    {
        "current_ms",
        py_current_ms,
        METH_NOARGS,
        "current_ms() -> int\n\n"
        "Get current time in milliseconds.\n\n"
        "Returns:\n"
        "    Current monotonic time in milliseconds (wraps at 32 bits)"
    },
    {nullptr, nullptr, 0, nullptr}
};

/*
 * Module Initialization (Multi-phase for free-threading support)
 */

/**
 * Module execution function.
 * Called during module import to set up types and constants.
 */
static int module_exec(PyObject* m) {
    // Finalize type
    if (PyType_Ready(&KCPSessionType) < 0) {
        return -1;
    }
    
    // Add KCPSession type
    Py_INCREF(&KCPSessionType);
    if (PyModule_AddObject(m, "KCPSession", 
            reinterpret_cast<PyObject*>(&KCPSessionType)) < 0) {
        Py_DECREF(&KCPSessionType);
        return -1;
    }
    
    // Add OVERHEAD constant
    if (PyModule_AddIntConstant(m, "OVERHEAD", KCP_OVERHEAD) < 0) {
        return -1;
    }
    
    return 0;
}

// Module slots for multi-phase initialization
static PyModuleDef_Slot module_slots[] = {
    {Py_mod_exec, reinterpret_cast<void*>(module_exec)},
    
    // Declare that this module supports free-threading (Python 3.13+)
#ifdef Py_mod_gil
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    
    {0, nullptr}
};

static struct PyModuleDef kcpmodule = {
    PyModuleDef_HEAD_INIT,
    /* m_name */        "_kcp",
    /* m_doc */         "KCP Protocol - Fast and Reliable ARQ Protocol",
    /* m_size */        0,
    /* m_methods */     module_methods,
    /* m_slots */       module_slots,
    /* m_traverse */    nullptr,
    /* m_clear */       nullptr,
    /* m_free */        nullptr,
};

// Module entry point
extern "C" PyMODINIT_FUNC PyInit__kcp(void) {
    return PyModuleDef_Init(&kcpmodule);
}