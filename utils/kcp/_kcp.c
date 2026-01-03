#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include "ikcp.h"

#include <string.h>
#include <stdlib.h>

#ifdef _WIN32
    #include <windows.h>
    #define MUTEX_TYPE          CRITICAL_SECTION
    #define MUTEX_INIT(m)       InitializeCriticalSection(&(m))
    #define MUTEX_DESTROY(m)    DeleteCriticalSection(&(m))
    #define MUTEX_LOCK(m)       EnterCriticalSection(&(m))
    #define MUTEX_UNLOCK(m)     LeaveCriticalSection(&(m))
    static inline IUINT32 iclock(void) {
        return (IUINT32)GetTickCount64();
    }
#else
    #include <pthread.h>
    #include <sys/time.h>
    #define MUTEX_TYPE          pthread_mutex_t
    #define MUTEX_INIT(m)       pthread_mutex_init(&(m), NULL)
    #define MUTEX_DESTROY(m)    pthread_mutex_destroy(&(m))
    #define MUTEX_LOCK(m)       pthread_mutex_lock(&(m))
    #define MUTEX_UNLOCK(m)     pthread_mutex_unlock(&(m))
    static inline IUINT32 iclock(void) {
        struct timeval tv;
        gettimeofday(&tv, NULL);
        return (IUINT32)(tv.tv_sec * 1000 + tv.tv_usec / 1000);
    }
#endif

/* ========================= Hard-coded Parameters ========================= */
#define KCP_NODELAY         1       /* Enable nodelay mode */
#define KCP_INTERVAL        10      /* Internal update interval (ms) */
#define KCP_RESEND          2       /* Fast resend trigger count */
#define KCP_NC              1       /* Disable congestion control */
#define KCP_SNDWND          256     /* Send window size */
#define KCP_RCVWND          256     /* Receive window size */
#define KCP_MTU             1400    /* Maximum transmission unit */
#define KCP_MINRTO          100      /* Minimum RTO (ms) */
#define KCP_DEADLINK        20      /* Max retransmit count before dead */
#define KCP_RECV_BUF_SIZE   65536   /* Receive buffer size */
#define KCP_STREAM_MODE     0       /* 0=message, 1=stream */
#ifndef IKCP_OVERHEAD
#define IKCP_OVERHEAD 24
#endif
/* ========================= KCPSession Object ========================= */

typedef struct {
    PyObject_HEAD
    ikcpcb *kcp;
    PyObject *output_func;          /* Callable: output(data: bytes) */
    void *user_data;                /* User context pointer */
    IUINT32 conv;
    MUTEX_TYPE lock;
    int dead;                       /* Connection dead flag */
} KCPSessionObject;

static PyTypeObject KCPSessionType;

/* Thread-safe lock helpers */
static inline void kcp_lock(KCPSessionObject *self) {
    MUTEX_LOCK(self->lock);
}

static inline void kcp_unlock(KCPSessionObject *self) {
    MUTEX_UNLOCK(self->lock);
}

/* KCP output callback - invoked when KCP needs to send UDP packet */
static int kcp_output_callback(const char *buf, int len, ikcpcb *kcp, void *user) {
    KCPSessionObject *self = (KCPSessionObject *)user;
    int result = 0;
    
    if (self->output_func == NULL || self->output_func == Py_None) {
        return -1;
    }
    
    /* Acquire GIL for Python callback */
    PyGILState_STATE gstate = PyGILState_Ensure();
    
    PyObject *data = PyBytes_FromStringAndSize(buf, len);
    if (data == NULL) {
        PyErr_Clear();
        result = -1;
        goto cleanup;
    }
    
    PyObject *ret = PyObject_CallOneArg(self->output_func, data);
    Py_DECREF(data);
    
    if (ret == NULL) {
        PyErr_Clear();
        result = -1;
    } else {
        Py_DECREF(ret);
    }
    
cleanup:
    PyGILState_Release(gstate);
    return result;
}

/* KCPSession.__new__ */
static PyObject *
KCPSession_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    KCPSessionObject *self = (KCPSessionObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->kcp = NULL;
        self->output_func = NULL;
        self->user_data = NULL;
        self->conv = 0;
        self->dead = 0;
    }
    return (PyObject *)self;
}

/* KCPSession.__init__(conv, output_func) */
static int
KCPSession_init(KCPSessionObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"conv", "output", NULL};
    IUINT32 conv;
    PyObject *output_func = NULL;
    
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "IO", kwlist, &conv, &output_func)) {
        return -1;
    }
    
    if (output_func != Py_None && !PyCallable_Check(output_func)) {
        PyErr_SetString(PyExc_TypeError, "output must be callable or None");
        return -1;
    }
    
    /* Initialize mutex */
    MUTEX_INIT(self->lock);
    
    /* Create KCP control block */
    self->kcp = ikcp_create(conv, self);
    if (self->kcp == NULL) {
        PyErr_SetString(PyExc_MemoryError, "Failed to create KCP instance");
        MUTEX_DESTROY(self->lock);
        return -1;
    }
    
    self->conv = conv;
    Py_XINCREF(output_func);
    self->output_func = output_func;
    
    /* Set output callback */
    self->kcp->output = kcp_output_callback;
    
    /* Apply hard-coded parameters */
    ikcp_nodelay(self->kcp, KCP_NODELAY, KCP_INTERVAL, KCP_RESEND, KCP_NC);
    ikcp_wndsize(self->kcp, KCP_SNDWND, KCP_RCVWND);
    ikcp_setmtu(self->kcp, KCP_MTU);
    self->kcp->rx_minrto = KCP_MINRTO;
    self->kcp->dead_link = KCP_DEADLINK;
    self->kcp->stream = KCP_STREAM_MODE;
    
    return 0;
}

/* KCPSession.__dealloc__ */
static void
KCPSession_dealloc(KCPSessionObject *self) {
    if (self->kcp != NULL) {
        ikcp_release(self->kcp);
        self->kcp = NULL;
    }
    Py_XDECREF(self->output_func);
    MUTEX_DESTROY(self->lock);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

/* KCPSession.send(data) -> int
   Send data through KCP. Returns bytes sent or < 0 on error. */
static PyObject *
KCPSession_send(KCPSessionObject *self, PyObject *args) {
    Py_buffer buf;
    
    if (!PyArg_ParseTuple(args, "y*", &buf)) {
        return NULL;
    }
    
    if (self->dead) {
        PyBuffer_Release(&buf);
        PyErr_SetString(PyExc_ConnectionError, "Connection is dead");
        return NULL;
    }
    
    kcp_lock(self);
    int ret = ikcp_send(self->kcp, buf.buf, (int)buf.len);
    kcp_unlock(self);
    
    PyBuffer_Release(&buf);
    
    if (ret < 0) {
        PyErr_SetString(PyExc_OSError, "KCP send failed");
        return NULL;
    }
    
    return PyLong_FromLong(ret);
}

/* KCPSession.recv(max_size=-1) -> bytes or None
   Receive data from KCP. Returns None if no data available. */
static PyObject *
KCPSession_recv(KCPSessionObject *self, PyObject *args) {
    int max_size = KCP_RECV_BUF_SIZE;
    
    if (!PyArg_ParseTuple(args, "|i", &max_size)) {
        return NULL;
    }
    
    if (max_size <= 0 || max_size > KCP_RECV_BUF_SIZE) {
        max_size = KCP_RECV_BUF_SIZE;
    }
    
    char *buffer = (char *)PyMem_Malloc(max_size);
    if (buffer == NULL) {
        return PyErr_NoMemory();
    }
    
    kcp_lock(self);
    int len = ikcp_recv(self->kcp, buffer, max_size);
    kcp_unlock(self);
    
    if (len < 0) {
        PyMem_Free(buffer);
        Py_RETURN_NONE;
    }
    
    PyObject *result = PyBytes_FromStringAndSize(buffer, len);
    PyMem_Free(buffer);
    return result;
}

/* KCPSession.input(data) -> int
   Feed received UDP data to KCP. Returns 0 on success, < 0 on error. */
static PyObject *
KCPSession_input(KCPSessionObject *self, PyObject *args) {
    Py_buffer buf;
    
    if (!PyArg_ParseTuple(args, "y*", &buf)) {
        return NULL;
    }
    
    kcp_lock(self);
    int ret = ikcp_input(self->kcp, buf.buf, (long)buf.len);
    kcp_unlock(self);
    
    PyBuffer_Release(&buf);
    
    return PyLong_FromLong(ret);
}

/* KCPSession.update() -> None
   Update KCP state. Must be called periodically. */
static PyObject *
KCPSession_update(KCPSessionObject *self, PyObject *Py_UNUSED(ignored)) {
    IUINT32 current = iclock();
    
    kcp_lock(self);
    ikcp_update(self->kcp, current);
    
    /* Check if connection is dead */
    if (self->kcp->state == (IUINT32)-1) {
        self->dead = 1;
    }
    kcp_unlock(self);
    
    Py_RETURN_NONE;
}

/* KCPSession.check() -> int
   Get milliseconds until next update is needed. */
static PyObject *
KCPSession_check(KCPSessionObject *self, PyObject *Py_UNUSED(ignored)) {
    IUINT32 current = iclock();
    
    kcp_lock(self);
    IUINT32 next_ts = ikcp_check(self->kcp, current);
    kcp_unlock(self);
    
    IUINT32 wait_ms = (next_ts > current) ? (next_ts - current) : 0;
    return PyLong_FromUnsignedLong(wait_ms);
}

/* KCPSession.flush() -> None
   Force flush all pending data. */
static PyObject *
KCPSession_flush(KCPSessionObject *self, PyObject *Py_UNUSED(ignored)) {
    kcp_lock(self);
    ikcp_flush(self->kcp);
    kcp_unlock(self);
    
    Py_RETURN_NONE;
}

/* KCPSession.waitsnd() -> int
   Get number of packets waiting to be sent. */
static PyObject *
KCPSession_waitsnd(KCPSessionObject *self, PyObject *Py_UNUSED(ignored)) {
    kcp_lock(self);
    int count = ikcp_waitsnd(self->kcp);
    kcp_unlock(self);
    
    return PyLong_FromLong(count);
}

/* KCPSession.peeksize() -> int
   Peek the size of next available message. Returns -1 if no message. */
static PyObject *
KCPSession_peeksize(KCPSessionObject *self, PyObject *Py_UNUSED(ignored)) {
    kcp_lock(self);
    int size = ikcp_peeksize(self->kcp);
    kcp_unlock(self);
    
    return PyLong_FromLong(size);
}

/* KCPSession.set_output(func) -> None
   Set or replace output callback. */
static PyObject *
KCPSession_set_output(KCPSessionObject *self, PyObject *args) {
    PyObject *func;
    
    if (!PyArg_ParseTuple(args, "O", &func)) {
        return NULL;
    }
    
    if (func != Py_None && !PyCallable_Check(func)) {
        PyErr_SetString(PyExc_TypeError, "output must be callable or None");
        return NULL;
    }
    
    kcp_lock(self);
    PyObject *old = self->output_func;
    Py_XINCREF(func);
    self->output_func = func;
    Py_XDECREF(old);
    kcp_unlock(self);
    
    Py_RETURN_NONE;
}

/* Property getters */
static PyObject *
KCPSession_get_conv(KCPSessionObject *self, void *closure) {
    return PyLong_FromUnsignedLong(self->conv);
}

static PyObject *
KCPSession_get_dead(KCPSessionObject *self, void *closure) {
    return PyBool_FromLong(self->dead);
}

static PyObject *
KCPSession_get_rto(KCPSessionObject *self, void *closure) {
    kcp_lock(self);
    IUINT32 rto = self->kcp->rx_rto;
    kcp_unlock(self);
    return PyLong_FromUnsignedLong(rto);
}

static PyObject *
KCPSession_get_srtt(KCPSessionObject *self, void *closure) {
    kcp_lock(self);
    IUINT32 srtt = self->kcp->rx_srtt;
    kcp_unlock(self);
    return PyLong_FromUnsignedLong(srtt);
}

static PyMethodDef KCPSession_methods[] = {
    {"send", (PyCFunction)KCPSession_send, METH_VARARGS,
     "send(data) -> int\nSend data through KCP."},
    {"recv", (PyCFunction)KCPSession_recv, METH_VARARGS,
     "recv(max_size=-1) -> bytes or None\nReceive data from KCP."},
    {"input", (PyCFunction)KCPSession_input, METH_VARARGS,
     "input(data) -> int\nFeed UDP packet to KCP."},
    {"update", (PyCFunction)KCPSession_update, METH_NOARGS,
     "update() -> None\nUpdate KCP state."},
    {"check", (PyCFunction)KCPSession_check, METH_NOARGS,
     "check() -> int\nGet ms until next update."},
    {"flush", (PyCFunction)KCPSession_flush, METH_NOARGS,
     "flush() -> None\nForce flush pending data."},
    {"waitsnd", (PyCFunction)KCPSession_waitsnd, METH_NOARGS,
     "waitsnd() -> int\nGet pending send count."},
    {"peeksize", (PyCFunction)KCPSession_peeksize, METH_NOARGS,
     "peeksize() -> int\nPeek next message size."},
    {"set_output", (PyCFunction)KCPSession_set_output, METH_VARARGS,
     "set_output(func) -> None\nSet output callback."},
    {NULL}
};

static PyGetSetDef KCPSession_getseters[] = {
    {"conv", (getter)KCPSession_get_conv, NULL, "Conversation ID", NULL},
    {"dead", (getter)KCPSession_get_dead, NULL, "Connection dead flag", NULL},
    {"rto", (getter)KCPSession_get_rto, NULL, "Current RTO in ms", NULL},
    {"srtt", (getter)KCPSession_get_srtt, NULL, "Smoothed RTT in ms", NULL},
    {NULL}
};

static PyTypeObject KCPSessionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_kcp.KCPSession",
    .tp_doc = PyDoc_STR("KCP Session - reliable UDP transport"),
    .tp_basicsize = sizeof(KCPSessionObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = KCPSession_new,
    .tp_init = (initproc)KCPSession_init,
    .tp_dealloc = (destructor)KCPSession_dealloc,
    .tp_methods = KCPSession_methods,
    .tp_getset = KCPSession_getseters,
};

/* ========================= Module Functions ========================= */

/* get_conv(data) -> int
   Extract conversation ID from KCP packet header. */
static PyObject *
kcp_get_conv(PyObject *module, PyObject *args) {
    Py_buffer buf;
    
    if (!PyArg_ParseTuple(args, "y*", &buf)) {
        return NULL;
    }
    
    if (buf.len < IKCP_OVERHEAD) {
        PyBuffer_Release(&buf);
        PyErr_SetString(PyExc_ValueError, 
            "Data too short for KCP packet (min 24 bytes)");
        return NULL;
    }
    
    IUINT32 conv = ikcp_getconv(buf.buf);
    PyBuffer_Release(&buf);
    
    return PyLong_FromUnsignedLong(conv);
}

/* current_ms() -> int
   Get current time in milliseconds. */
static PyObject *
kcp_current_ms(PyObject *module, PyObject *Py_UNUSED(ignored)) {
    return PyLong_FromUnsignedLong(iclock());
}

static PyMethodDef kcp_module_methods[] = {
    {"get_conv", kcp_get_conv, METH_VARARGS,
     "get_conv(data) -> int\nExtract conv ID from KCP packet."},
    {"current_ms", kcp_current_ms, METH_NOARGS,
     "current_ms() -> int\nGet current time in milliseconds."},
    {NULL}
};

/* ========================= Module Definition ========================= */

static int
kcp_module_exec(PyObject *module) {
    if (PyType_Ready(&KCPSessionType) < 0) {
        return -1;
    }
    
    Py_INCREF(&KCPSessionType);
    if (PyModule_AddObject(module, "KCPSession", (PyObject *)&KCPSessionType) < 0) {
        Py_DECREF(&KCPSessionType);
        return -1;
    }
    
    /* Add constants */
    if (PyModule_AddIntConstant(module, "OVERHEAD", IKCP_OVERHEAD) < 0) {
        return -1;
    }
    
    return 0;
}

static PyModuleDef_Slot kcp_module_slots[] = {
    {Py_mod_exec, kcp_module_exec},
#ifdef Py_MOD_PER_INTERPRETER_GIL_SUPPORTED
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
#ifdef Py_mod_gil
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},  /* Free-threaded support */
#endif
    {0, NULL}
};

static struct PyModuleDef kcp_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_kcp",
    .m_doc = "KCP Protocol - Fast and Reliable ARQ Protocol",
    .m_size = 0,
    .m_methods = kcp_module_methods,
    .m_slots = kcp_module_slots,
};

PyMODINIT_FUNC
PyInit__kcp(void) {
    return PyModuleDef_Init(&kcp_module);
}