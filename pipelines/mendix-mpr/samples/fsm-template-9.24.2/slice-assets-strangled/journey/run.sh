#!/bin/bash
# runs a journey with credentials read from the machine-local mxcli constant stores (never printed)
J=$1; shift
eval "$(python3 - <<'PY'
import json,shlex
c=json.load(open('<lab>/web-assets/mono/.mxcli/constants.json'))['constants']
print('export JOURNEY_PW='+shlex.quote(c['AssetsSeam.JourneyUserPassword']))
print('export MONO_API_USER=assets_slice MONO_API_PW='+shlex.quote(c['CoreSeam.SliceAPIUserPassword']))
print('export SLICE_API_USER=fsm_monolith SLICE_API_PW='+shlex.quote(c['AssetsSeam.APIUserPassword']))
PY
)"
export SLICE_MPR=<lab>/web-assets/AssetsApp/AssetsApp.mpr MONO_MPR=<lab>/web-assets/mono/fsm.mpr
export MXCLI=<lab>/mxcli PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH=/opt/node-tools/node_modules OUT_DIR=$(dirname $0)
s=$(date +%s); node $J; e=$?; echo "exit=$e wall $(( $(date +%s)-s )) s"
