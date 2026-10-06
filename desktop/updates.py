"""Run Sparkle in the editor's native macOS event loop."""
from pathlib import Path
import sys


def start_updater():
    """Keep the controller alive for the lifetime of a packaged application."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    import objc
    from Foundation import NSBundle

    bundle = NSBundle.mainBundle()
    framework = Path(bundle.bundlePath()) / "Contents/Frameworks/Sparkle.framework"
    objc.loadBundle("Sparkle", globals(), bundle_path=str(framework))
    controller_class = objc.lookUpClass("SPUStandardUpdaterController")
    controller = controller_class.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
        True, None, None
    )
    if controller.updater().automaticallyChecksForUpdates():
        controller.updater().checkForUpdatesInBackground()
    return controller
