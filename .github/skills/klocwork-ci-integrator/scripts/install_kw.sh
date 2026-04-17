#=====================================================================
# Copyright(c) 2018 - 2021 Intel Corporation
#
# For licensing information, see the file 'LICENSE' in the root folder
# ====================================================================

#!/bin/bash

MEV_COMMON_PROFILE=/home/sys_sysfw/.mev_common_profile
DIR="/home/sys_sysfw/klocwork"
if [ ! -d "$DIR" ]; then
  # Take action if $DIR does not exist. #
  echo "Installing config files in ${DIR}..."
  echo "PATH=~/klocwork/bin:\$PATH" >> $MEV_COMMON_PROFILE
  mkdir -p "$DIR" # create the installation directory
  /mnt/ci_tools/kw-server-installer.20.1.0.97.linux64.sh -a --license-server kwlic.intel.com:7500 $DIR
  cp -f /mnt/ci_tools/java_wrappers_memory.conf $DIR/config/
  cp /mnt/ci_tools/ltoken $DIR
  chown -R sys_sysfw:sys_sysfw $DIR
  echo "kw installtion completed"
fi
