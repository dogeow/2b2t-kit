#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p work/module-cache
swiftc -swift-version 5 -module-cache-path work/module-cache Sources/HTTPProtocol.swift Sources/LanguageIdentity.swift Sources/ServiceDiagnostics.swift Sources/TranslationQueue.swift Sources/LocalServer.swift Tests/main.swift -framework NaturalLanguage -framework Network -o work/protocol-tests
work/protocol-tests
