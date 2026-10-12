#!/bin/bash
# Manual M2EE start of the Mendix 9.24.2 monolith copy (mxcli run cannot: it forces JDK 21; the 9.24 runtime requires Java 11).
R=$HOME/.mxcli/runtime/9.24.2.6130/runtime
export MX_INSTALL_PATH=$HOME/.mxcli/runtime/9.24.2.6130 MX_LOG_LEVEL=i M2EE_ADMIN_PORT=8390 M2EE_ADMIN_PASS="${M2EE_ADMIN_PASS:?set a local admin password}"
exec /usr/lib/jvm/java-11-openjdk-amd64/bin/java -Dfile.encoding=UTF-8 -Xmx1g -jar $R/launcher/runtimelauncher.jar <lab>/seam/mono9/deployment
