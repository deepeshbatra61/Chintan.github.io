import Foundation
import AuthenticationServices
import Capacitor

/// A local, dependency-free Sign in with Apple bridge.
///
/// WHY THIS EXISTS RATHER THAN A COMMUNITY PLUGIN: @capacitor-community/apple-sign-in
/// tops out at 7.1.0, built against Capacitor 7's Swift package -- this project runs
/// Capacitor 8, and Swift Package Manager cannot resolve two incompatible versions of
/// the same package in one graph. That mismatch is what "No such module 'Capacitor'"
/// actually was: not a build glitch, a real, unfixed gap in the plugin's release
/// history. Writing directly against Apple's own AuthenticationServices framework
/// sidesteps the problem instead of working around it -- there is no third-party
/// Capacitor-version pin left to go stale on the next upgrade.
///
/// The JS side (LoginPage.js) reaches this via window.Capacitor.Plugins.SignInWithApple
/// exactly as it would a normal Capacitor plugin -- CAPBridgedPlugin conformance is
/// enough for Capacitor's runtime to auto-discover this class, no separate
/// registration file or JS package needed.
@objc(SignInWithApplePlugin)
public class SignInWithApplePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "SignInWithApplePlugin"
    public let jsName = "SignInWithApple"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "authorize", returnType: CAPPluginReturnPromise)
    ]

    // Kept alive for the duration of one authorization -- ASAuthorizationController
    // holds only a weak reference to its delegate, so letting this fall out of scope
    // mid-flow silently drops the callback. One in-flight call at a time is all this
    // plugin needs to support.
    private var pendingDelegate: AuthDelegate?

    @objc func authorize(_ call: CAPPluginCall) {
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = [.fullName, .email]

        let controller = ASAuthorizationController(authorizationRequests: [request])
        let delegate = AuthDelegate(call: call, plugin: self)
        controller.delegate = delegate
        controller.presentationContextProvider = delegate
        pendingDelegate = delegate
        controller.performRequests()
    }

    fileprivate func finish() {
        pendingDelegate = nil
    }
}

private class AuthDelegate: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private let call: CAPPluginCall
    private weak var plugin: SignInWithApplePlugin?

    init(call: CAPPluginCall, plugin: SignInWithApplePlugin) {
        self.call = call
        self.plugin = plugin
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        defer { plugin?.finish() }

        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            call.reject("Unexpected Apple credential type")
            return
        }
        guard let tokenData = credential.identityToken,
              let identityToken = String(data: tokenData, encoding: .utf8) else {
            call.reject("Apple did not return an identity token")
            return
        }

        // Apple sends the name ONLY on the account's very first authorization on this
        // device -- absent on every sign-in after. If the caller doesn't capture it
        // here, it's gone permanently, so it's forwarded even when empty/nil.
        call.resolve([
            "identityToken": identityToken,
            "givenName": credential.fullName?.givenName ?? "",
            "familyName": credential.fullName?.familyName ?? "",
            "user": credential.user,
        ])
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        defer { plugin?.finish() }

        let nsError = error as NSError
        // ASAuthorizationError.canceled -- the user dismissing Apple's sheet is
        // routine, not a failure. Surfaced with a distinct code so the JS side
        // (LoginPage.js's handleAppleLogin) can recognise it and stay silent
        // rather than showing an error toast for someone simply changing their mind.
        if nsError.domain == ASAuthorizationError.errorDomain,
           nsError.code == ASAuthorizationError.canceled.rawValue {
            call.reject("Sign in with Apple was cancelled", "1001")
            return
        }
        call.reject(error.localizedDescription, String(nsError.code))
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        return plugin?.bridge?.viewController?.view.window ?? ASPresentationAnchor()
    }
}
