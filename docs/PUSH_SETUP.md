# Push notifications: setup (owner)

Push is built and switched **off**. Nothing reaches a phone until every step
below is done and you turn it on from the Desk (chintan.news/admin → Push).
Never paste any of these keys into a chat; set them yourself.

## 1. Firebase project (once, ~10 min)

1. Go to https://console.firebase.google.com → **Add project** → name it
   `Chintan`. Google Analytics: off (not needed).
2. **Add app → Android**. Package name: `com.chintan.app`. Nickname: Chintan
   Android. Skip the SHA step. Download **google-services.json**.
3. Put it at `frontend/android/app/google-services.json` on the machine that
   builds Android. It is git-ignored on purpose (public repo), so keep a copy.
4. **Add app → iOS**. Bundle ID: `com.chintan.app`. Download
   **GoogleService-Info.plist** and send it to Bani for the Mac build.

## 2. Server key for Railway (the backend sends through Firebase)

1. Firebase console → ⚙ **Project settings → Service accounts → Generate new
   private key**. A JSON file downloads. Treat it like a password.
2. Railway → the backend service → **Variables → New variable**:
   - `FIREBASE_SERVICE_ACCOUNT` = the whole JSON file's contents (paste as is).
   - `PUSH_TEST_USER_EMAIL` = the app account email you test with.
   - Optional: `PUSH_ALERT_EMAIL` = where failure alerts go (defaults to
     `ADMIN_EMAILS`).
   - Optional hard off: `PUSH_ENABLED=false` stops everything, whatever the
     Desk switch says.
3. Delete the downloaded JSON from Downloads once it's in Railway.

The Desk's Push panel says "Firebase isn't configured on the server" until
`FIREBASE_SERVICE_ACCOUNT` is set.

## 3. Apple push key (for iPhones)

1. https://developer.apple.com/account → **Certificates, IDs & Profiles →
   Keys → +**. Name: `Chintan Push`. Tick **Apple Push Notifications service
   (APNs)** → Continue → Register → **Download** the `.p8` (only downloadable
   once). Note the **Key ID** and your **Team ID** (top right of the page).
2. Firebase console → Project settings → **Cloud Messaging → Apple app
   configuration → APNs Authentication Key → Upload**: the `.p8`, Key ID,
   Team ID.

## 4. Android build (vc15)

1. `frontend/android/app/google-services.json` in place (step 1).
2. Bump `versionCode 15`, `versionName "1.12.0"` in `frontend/android/app/build.gradle`.
3. `cd frontend`, `npm run build`, `npx cap sync android`, then build the
   release bundle in Android Studio as usual.
4. **Before uploading to Play:** update the privacy policy and Play's **Data
   safety** form (below).

## 5. iOS build (Bani, on the Mac)

1. `npx cap sync ios` (adds the push plugin pod).
2. In `ios/App/Podfile`, inside `target 'App'`, add `pod 'FirebaseMessaging'`,
   then `cd ios/App && pod install`.
3. Xcode: drag **GoogleService-Info.plist** into the `App` group (tick "Copy
   items if needed", target App).
4. Xcode → App target → **Signing & Capabilities → + Capability**:
   **Push Notifications**, and **Background Modes** with **Remote
   notifications** ticked.
5. Replace the three functions below in `ios/App/App/AppDelegate.swift` (keep
   the rest of the file). Without this, iPhones report Apple's token, which
   Firebase can't send to.

```swift
import UIKit
import Capacitor
import FirebaseCore
import FirebaseMessaging

// in class AppDelegate:

func application(_ application: UIApplication,
                 didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
    FirebaseApp.configure()
    return true
}

func application(_ application: UIApplication,
                 didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    // Hand Apple's token to Firebase, then give the app the Firebase token.
    Messaging.messaging().apnsToken = deviceToken
    Messaging.messaging().token { token, error in
        if let error = error {
            NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
        } else if let token = token {
            NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: token)
        }
    }
}

func application(_ application: UIApplication,
                 didFailToRegisterForRemoteNotificationsWithError error: Error) {
    NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
}
```

6. Bump the build number and archive as usual.

## 6. Privacy policy + Play Data safety (before vc15 goes out)

- **Privacy policy**, add: "If you turn on notifications, we store a device
  token issued by Google Firebase / Apple, your device's time zone and your
  notification choices, to send the briefs and alerts you asked for. We record
  when a notification is delivered and opened to improve timing. Turning
  notifications off or signing out removes this device's token."
- **Play Console → App content → Data safety**, add:
  - *Device or other IDs*: collected, not shared, purpose **App functionality**
    (push delivery), marked **optional** (readers choose to turn it on).
  - *App activity → App interactions*: notification opens, purpose
    **Analytics** and **App functionality**.

## 7. Go live

1. Install the new build, finish an article, say yes to the sheet.
2. Desk → Push → **Send a test push to my devices**. It should say
   "Android · delivered" and the phone should show "Surya's up. This is a test."
3. Desk → Push → **Turn push on…** → confirm. The next slot sends.
4. To stop at any moment: **Turn push off** (instant).

## Copy eval (whenever the push prompt changes)

```
cd backend
.venv-test\Scripts\python scripts\eval_push_copy.py
```

Needs `ANTHROPIC_API_KEY` set in that shell. Fails if any sad or sensitive
story would get anything but plain copy; prints the rest for you to judge.
