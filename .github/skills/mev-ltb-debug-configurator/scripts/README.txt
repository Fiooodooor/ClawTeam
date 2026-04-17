Purpose
========
The purpose of this page is to explain how to use python script which attaches LTB to the silicone.
Also the internal structure of script is described in the article.

Overview
======== 
The main purpose of the script is is to configure environment and T32 (Trace32) application.
Silicone will be configured dependent on the project. For example if user need to debug MEV-TS using A0 HW , he should disable  erot_preset = 0 bit in fuse_forse2 register. 
From the other hand if user need to debug MEV-1 project this action is not requested.
Script divided to three stages:
  1.Configure environment:
  2.Configure Trace32 application 
  3.Resume CPU which halted  in stage 1 

After script finished execution the CPU will be stopped at the very beginning of the Boot ROM instruction. This will be indication that script executed successfully.

Pre-condition
=============
Install FTDI device driver for windows:
Can be done in CMD or POWER SHELL 
PS C:\Users\laduser> pip install ftd2xx
Cache Credentials
During script execution user asked to unlock unit several times. User should manually add credentials in order to unlock unit. This can be prevented by caching credentials. 
Please follow the wiki in order to Cache Credentials
Cache Credentials


Execution of the script 
========================
For MEV project execute script with "CfgDebugEnv.py" with "mev" parameter as show below.
	$>py CfgDebugEnv.py mev
	
For MEV-TS using  A0 HW project execute script with "CfgDebugEnv.py" with "mev_ts" parameter as show below.
    $>py CfgDebugEnv.py mev_ts

Wiki
======
URL:https://wiki.ith.intel.com/pages/viewpage.action?pageId=2059015057