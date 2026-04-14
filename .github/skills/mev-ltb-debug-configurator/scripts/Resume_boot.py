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
import os, sys
import time
from struct import *


# remove error output
sys.stderr = open(os.devnull, 'w')

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


if __name__ == "__main__":
    #initialize objects and protocols
    #initialize OpenIPC
    ipc = ipccli.baseaccess()
    # initialize SV object
    sv = get_sv()
    ipc.unlock()
    resume_boot()
