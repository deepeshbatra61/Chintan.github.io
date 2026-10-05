#!/bin/bash
# One command for an iPhone release, run on the Mac from anywhere:
#
#   bash ~/Documents/Chintan.github.io/frontend/scripts/ios-release.sh
#
# It pulls the latest code, installs packages, builds the app, copies it into
# the iOS project, sets the version from src/lib/appVersion.js, raises the
# build number by one, and opens Xcode. In Xcode you then only do:
#   Product -> Archive -> Distribute App -> App Store Connect -> Upload
set -euo pipefail

FRONTEND="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FRONTEND"

step() { printf "\n\033[1;31m==>\033[0m %s\n" "$1"; }

step "Getting the latest code"
git -C "$FRONTEND/.." pull --ff-only

step "Installing packages"
npm install --no-audit --no-fund

step "Building the app"
npx craco build

step "Copying it into the iPhone project"
npx cap sync ios

VERSION="$(sed -n 's/.*APP_VERSION = "\([0-9.]*\)".*/\1/p' src/lib/appVersion.js)"
PBX="ios/App/App.xcodeproj/project.pbxproj"
if [ -f "$PBX" ] && [ -n "$VERSION" ]; then
  step "Setting version $VERSION and the next build number"
  BUILD="$(sed -n 's/.*CURRENT_PROJECT_VERSION = \([0-9]*\);.*/\1/p' "$PBX" | sort -n | tail -1)"
  NEXT=$(( ${BUILD:-0} + 1 ))
  sed -i '' "s/MARKETING_VERSION = [^;]*;/MARKETING_VERSION = $VERSION;/g" "$PBX"
  sed -i '' "s/CURRENT_PROJECT_VERSION = [0-9]*;/CURRENT_PROJECT_VERSION = $NEXT;/g" "$PBX"
  echo "Version $VERSION, build $NEXT"
  echo "If App Store Connect says this build number was already used, raise Build by one in Xcode."
else
  echo "Couldn't find the iOS project or the app version; set Version/Build in Xcode by hand."
fi

step "Opening Xcode"
npx cap open ios
echo
echo "In Xcode: choose 'Any iOS Device (arm64)', then Product -> Archive -> Distribute App -> App Store Connect -> Upload."
