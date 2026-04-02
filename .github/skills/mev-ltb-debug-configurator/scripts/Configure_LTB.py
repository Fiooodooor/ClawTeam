import ctypes # module for C data types
import enum # module for enumeration support
import time

# Load TRACE32 Remote API DLL
t32api = ctypes.cdll.LoadLibrary('t32api64.dll')
# TRACE32 Debugger or TRACE32 Instruction Set Simulator as debug device
T32_DEV = 0
# Configure communication channel to the TRACE32 device
# use b for byte encoding of strings
t32api.T32_Config(b"NODE=",b"localhost")
t32api.T32_Config(b"PORT=",b"20000")
t32api.T32_Config(b"PACKLEN=",b"1024")
# Establish communication channel
rc = t32api.T32_Init()
rc = t32api.T32_Attach(T32_DEV)
rc = t32api.T32_Ping()
rc = t32api.T32_Cmd(b"DO ~~/scripts/launch_ip_by_name.cmm NAME=DAP")
time.sleep(5)
rc = t32api.T32_Exit()
t32api.T32_Config(b"NODE=",b"localhost")
t32api.T32_Config(b"PACKLEN=",b"1024")
t32api.T32_Config(b"PORT=",b"20010")
rc = t32api.T32_Init()
rc = t32api.T32_Attach(0)
rc = t32api.T32_Ping()
print(rc)
rc = t32api.T32_Cmd(b"DO ~~/scripts/DAP_config.cmm")
print(rc)
time.sleep(3)
rc = t32api.T32_Cmd_f(b"SYStem.Up")
print(rc)
# TRACE32 control commands
# Release communication channel
rc = t32api.T32_Exit()

