import ctypes

kernel32 = ctypes.windll.kernel32

HIGH_PRIORITY_CLASS = 0x00000080
THREAD_PRIORITY_HIGHEST = 2

def apply_latency_optimizations():
    try:
        proc = kernel32.GetCurrentProcess()
        res1 = kernel32.SetPriorityClass(proc, HIGH_PRIORITY_CLASS)
        
        thread = kernel32.GetCurrentThread()
        res2 = kernel32.SetThreadPriority(thread, THREAD_PRIORITY_HIGHEST)
        
        print(f"✅ Process High Priority: {bool(res1)}, Thread Highest Priority: {bool(res2)}")
    except Exception as e:
        print(f"Priority boost exception: {e}")

if __name__ == "__main__":
    apply_latency_optimizations()
