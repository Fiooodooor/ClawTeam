#************************************************************************************************************
# INTEL CONFIDENTIAL
# Copyright 4/29/15 Intel Corporation All Rights Reserved.
# The source code contained or described herein and all documents related to the source code 
# ("Material") are owned by Intel Corporation or its suppliers or licensors. 
# Title to the Material remains with Intel Corporation or its suppliers and licensors. 
# The Material contains trade secrets and proprietary 
# and confidential information of Intel or its suppliers and licensors. 
# The Material is protected by worldwide copyright and trade secret laws and treaty provisions. 
# No part of the Material may be used, copied, reproduced, modified, published, uploaded,
# posted, transmitted, distributed, or disclosed in any way without Intel's prior express written permission.
# No license under any patent, copyright, trade secret or other intellectual property
# right is granted to or conferred upon you by disclosure or delivery of the Materials,
# either expressly, by implication, inducement, estoppel or otherwise. 
# Any license under such intellectual property rights must be express and approved by Intel in writing.
#************************************************************************************************************


# libraries imports
from mtevans import get_sv
import ipccli
import os
# FTDI device driver
import sys, ftd2xx as ftd
import time
import argparse
from struct import *
import argparse
from CfgDebugEnv import MountX

#*****************************************************************************************************
# index of MEV device
# Indx DID         Alias              Type                Step Idcode      P/D/ C/T  Enabled
# --------------------------------------------------------------------------------------------------
# 0    0x00004000  MEV_CLTAPC0        MEV_CLTAPC          A0   0x000E3113   -/-/ -/-  Yes
#*****************************************************************************************************
MEV_CLTAPC0_index = 0
SET_HOOK_DISABLE = 0
SET_HOOK_ENABLE = 1
HOOK = 3
IS_MEV_TS = 0

# remove error output
sys.stderr = open(os.devnull, 'w')


#********************************************
# Scan and force reconfig the devi
#********************************************
def scan_and_forcereconfig():
    try:
        print("[info] Start scan_and_forcereconfig")
        # Perform device scan before reconfig
        # not always first time is successful
        # Generaly need 3 scans
        for x in range(6):
            v = ipc.irdrscan("MEV_CLTAPC0", 0xf0, 2, 2)
            if v == 0x2:
                break
        #Requests a topology update from the IPC API. When the topology update
        #occurs we will refresh the entire devicelist and node structure.
        ipc.forcereconfig()
    except Exception as e:
        print("[info] Exeption thrown during scan_and_forcereconfig operation")

def forcereconfig():
    try:
        ipc.forcereconfig()
    except Exception as e:
        print("[info] Exeption thrown during forcereconfig() operation")


class FTDI_dev:
  def __init__(self):
    self.FTDI_devices = ftd.open(self.get_devise())

  def get_devise(self):
      index = -1
      devices = ftd.listDevices()
      for x in range(len(devices)):
          description = ftd.getDeviceInfoDetail(x).get('description').decode("utf-8")
          if "Pisga" in description and "B" in description:
              index = x
              break
      if index == -1:
          print("Device not found script will be terminated")
          sys.exit()
      return index
              
  def power_down(self):
    # Power down same as to see 0 to address 0x200 on BOBCAT
    self.FTDI_devices.write(b'\x02\x00\x00\n\x00\x00\x00\x02\x00\x01\x00\x00\x00\x00')
    time.sleep(5)

  def power_up(self):
    # Power up same as to see 1 to address 0x200 on BOBCAT
    self.FTDI_devices.write(b'\x02\x00\x00\n\x00\x00\x00\x02\x00\x01\x00\x00\x00\x01')
    time.sleep(5)

  def power_lan_good(self):
    print("[info] power_lan_good ")
    self.power_down()
    # sleep one second befor power up
    time.sleep(1)
    self.power_up()
    time.sleep(10)
    print("[info] power_lan_good done")



#********************************************
# prevent CPU boot proces
#********************************************
def hold_cpu():
    print("[info] hold_cpu_en")
    # Hold one of the eight ITP hook pins in the specified state.
    # This command will prevent CPU from booting
    ipc.holdhook(MEV_CLTAPC0_index,HOOK,SET_HOOK_ENABLE) # set boot_halt strap

#********************************************
# exit CPU hold mode
#********************************************
def disable_hold_cpu():
    print("[info] disable_hold_cpu")
    # Hold one of the eight ITP hook pins in the specified state.
    # This command will remove CPU hold hook
    ipc.holdhook(MEV_CLTAPC0_index,HOOK,SET_HOOK_DISABLE)

#********************************************
# disable erot
#********************************************
def disable_erot_replase():
    try:
        print("[info] disable_erot_replase")
        # this command change state oof erort_replase to high
        # this means that PFUSE will be configured accordigly to this bit
        sv.mev.imc.syscon.syscon_mem.fuse_force2.erot_replace=0
        # Force fuse owerride
        #sv.mev.imc.syscon.syscon_mem.fuse_force.fuse_force_enable=1
    except Exception as e:
        print("!!! Handling Exception during disable_erot_replase")
        # If some thing went wrong reset enviroment and try again
        reset_enviroment()
        try:
            sv.mev.imc.syscon.syscon_mem.fuse_force2.erot_replace=0
            #sv.mev.imc.syscon.syscon_mem.fuse_force.fuse_force_enable=1
        except Exception as e:
            print("!!! Exception thrown during disable_erot_replase after reset\
                to enviroment performed")

#********************************************
# In case something go wrong reset enviroment
#********************************************
def ipc_reconect():
    print("[info] ipc reconnect")
    # Disconnects from the IPC, waits for the specified number of seconds,
    # then re-connects and re-initializes the IPC-CLI.
    ipc.reconnect()

#********************************************
# In case something go wrong reset enviroment
#********************************************
def reset_enviroment():
    print("[info] reset_enviroment")
    ipc_reconect()
    # Force the CLTAP to control the debug port (instead of APB controlling it)
    # 1. Sets sv.mev.taps.cltapc_imc.extportforce=1 to give the debug port ownership of the tap network
    # 2. Calls ipc.forceconfig() to have OpenIPC reinitialize and discover the tap network (any errors here are ignored, see stop_on_error)
    # 3. Calls sv.refresh() to have PythonSV refresh the namednodes given the new hierarchy
    sv.mev.taps.forcecltap()


#********************************************
# continue boot
#********************************************
def perform_imcr():
    print("[info] Perform IMCR reset")
    sv.mev.imc.syscon.syscon_mem.reset_ctl.resetchip=1
    time.sleep(2)


#********************************************
# Perform RED unlock
#********************************************
def unlock():
    try:
        print("Try to unlock...")
        ipc.unlock()
    except Exception as e:
        print("[info] Exception thrown during unlock")

#********************************************
# resume boot process
#********************************************
def resume_boot():
    print("[info] set_tap_ctrl_resume")
    print("[info] Continue boot flow")
    # resume1 -- Control to assert Early Boot Debug Exit when boothalt is asserted.
    sv.mev.taps.parimcnicdfxlegn_dfxagg_tap.tap_ctrl.resume0=0x1
    # resume0 -- Control to assert Early Boot Debug Exit when boothalt is asserted.
    sv.mev.taps.parimcnicdfxlegn_dfxagg_tap.tap_ctrl.resume1=0x1
    time.sleep(2)

def ltb_instruction_message():
    print('*********************************************************************************')
    print('*   1. At this stage go to LTB window                                           *')
    print('*   2. Start secondary debugger Intel->DAP                                      *')
    print('*   3. Execute script [DAP_config.cmm]                                          *')
    print('*   4. After script finished please press radio button [UP]                     *')
    print('*   5. Status of LTB should chage to  [emulation running]                       *')
    print('*   6. After that back to script and pressany button in order to release CPU    *')
    print('*********************************************************************************')
    input("Press enter to continue after LTB configured accordinglly to instruction above")
def main():
    print("[info] start main")
    dev=FTDI_dev()
    if IS_MEV_TS == MountX.MEV_TS:
        dev.power_down()
        forcereconfig()
        dev.power_up()
    reset_enviroment()
    scan_and_forcereconfig()
    hold_cpu()
    dev.power_lan_good()
    ipc_reconect()
    unlock()
    if IS_MEV_TS == MountX.MEV_TS:
        resume_boot()
        disable_erot_replase()
        perform_imcr()
        ipc_reconect()
        unlock()
    forcereconfig()
    #ltb_instruction_message()
    #resume_boot()
    print("[info] End of main")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('prj', type=MountX.argparse, choices=list(MountX))
    args = parser.parse_args()
    print(args.prj)
    print(type(args.prj))
    IS_MEV_TS = args.prj
    #initialize objects and protocols
    #initialize OpenIPC
    ipc = ipccli.baseaccess()
    # initialize SV object
    sv = get_sv()
    #main flow
    main()
    























