import threading
from datetime import datetime

from engine.control.safety import EmergencyStop
from engine.control.permission_manager import PermissionManager
from vision.screenshot_service import ScreenshotService
from vision.vision_analyzer import VisionAnalyzer
from vision.privacy_guard import PrivacyGuard


class ScreenObserver:

    def __init__(self):
        self._requests = {}
        self._screenshot_service = ScreenshotService()
        self._vision_analyzer = VisionAnalyzer()
        self._privacy_guard = PrivacyGuard()
        self._permission_manager = PermissionManager()
        self._lock = threading.Lock()
        self._request_counter = 0

    def request_observation(self, reason, source="user_request"):
        if EmergencyStop.is_engaged():
            return {
                "ok": False,
                "error": "Emergency stop is engaged. Cannot create observation.",
            }

        with self._lock:
            self._request_counter += 1
            request_id = f"obs_{int(datetime.now().timestamp())}_{self._request_counter}"
            request = {
                "request_id": request_id,
                "reason": reason,
                "source": source,
                "requires_permission": True,
                "permission_granted": False,
                "allow_cloud_analysis": False,
                "store_screenshot": False,
                "created_at": datetime.now().isoformat(),
                "screenshot_data": None,
                "privacy_check": None,
                "status": "pending",
            }
            self._requests[request_id] = request
            return request

    def request_trusted_read_only(self, reason, source="user_request"):
        if EmergencyStop.is_engaged():
            return {
                "ok": False,
                "summary": "Emergency stop is engaged. Cannot observe screen.",
                "analysis": None,
                "request_id": None,
                "error": "Emergency stop is engaged. Cannot observe screen.",
                "data": {
                    "type": "screen_observation",
                    "requires_permission": False,
                    "trusted_read_only": True,
                },
            }

        with self._lock:
            self._request_counter += 1
            request_id = f"obs_{int(datetime.now().timestamp())}_{self._request_counter}"
            request = {
                "request_id": request_id,
                "reason": reason,
                "source": source,
                "requires_permission": False,
                "permission_granted": True,
                "allow_cloud_analysis": False,
                "store_screenshot": False,
                "created_at": datetime.now().isoformat(),
                "screenshot_data": None,
                "privacy_check": None,
                "status": "approved",
                "trusted_read_only": True,
            }
            self._requests[request_id] = request

        screenshot = self._screenshot_service.capture_real()
        privacy_result = self._privacy_guard.check_payload(screenshot)

        request["screenshot_data"] = self._capture_metadata(screenshot)
        request["privacy_check"] = privacy_result

        analysis = self._vision_analyzer.analyze(screenshot, allow_cloud=False)
        if privacy_result.get("sensitive_content_detected"):
            analysis["sensitive_content_detected"] = True
            analysis["possible_issue"] = privacy_result.get("reason", "Sensitive content detected")

        request["analysis_result"] = analysis
        request["status"] = "completed" if analysis.get("ok") else "unavailable"

        summary = analysis.get("summary", "Screen observed in trusted read-only mode.")
        if not analysis.get("ok"):
            summary = f"Screen vision unavailable: {analysis.get('error') or 'capture failed'}"

        return {
            "ok": bool(analysis.get("ok")),
            "summary": summary,
            "message": summary,
            "analysis": analysis,
            "request_id": request_id,
            "data": {
                "type": "screen_observation",
                "requires_permission": False,
                "trusted_read_only": True,
                "observation": {
                    "request_id": request_id,
                    "status": request["status"],
                    "summary": summary,
                    "detected_context": analysis.get("detected_context", "unknown"),
                    "screenshot_method": screenshot.get("method", "unknown"),
                    "sensitive_content_detected": privacy_result.get("sensitive_content_detected", False),
                    "allow_cloud_analysis": False,
                    "store_screenshot": False,
                },
            },
        }

    def observe_screen(self, reason, source="owner_request", allow_cloud=True):
        """Real capture + real analysis in one call, for the OWNER.

        request_trusted_read_only is the conservative real-capture, local-only preview.
        This owner path can use cloud analysis when explicitly allowed: NEXI grabs the real
        screen and, with allow_cloud, describes it via the multimodal brain — the owner
        consents by being the owner and asking. The privacy guard still redacts any
        secret in the model's description before it is returned or spoken.
        """
        if EmergencyStop.is_engaged():
            return {
                "ok": False,
                "summary": "Emergency stop is engaged. Cannot observe screen.",
                "analysis": None,
                "request_id": None,
                "error": "Emergency stop is engaged.",
                "data": {"type": "screen_observation", "owner_vision": True},
            }

        with self._lock:
            self._request_counter += 1
            request_id = f"obs_{int(datetime.now().timestamp())}_{self._request_counter}"

        screenshot = self._screenshot_service.capture_real()     # REAL capture (owner intent)
        privacy_result = self._privacy_guard.check_payload(screenshot)
        analysis = self._vision_analyzer.analyze(screenshot, allow_cloud=allow_cloud)
        # Sensitive content can be flagged at two points: the screenshot's own
        # visible_text (usually empty here) OR the model's description of the screen
        # (where a redacted key actually shows up). Report the OR so the flag matches
        # what was redacted from the summary.
        sensitive = bool(privacy_result.get("sensitive_content_detected")
                         or analysis.get("sensitive_content_detected"))
        analysis["sensitive_content_detected"] = sensitive
        if privacy_result.get("sensitive_content_detected"):
            analysis["possible_issue"] = privacy_result.get("reason", "Sensitive content detected")

        with self._lock:
            self._requests[request_id] = {
                "request_id": request_id,
                "reason": reason,
                "source": source,
                "permission_granted": True,
                "status": "completed" if analysis.get("ok") else "unavailable",
                "screenshot_data": self._capture_metadata(screenshot),
                "privacy_check": privacy_result,
                "analysis_result": analysis,
                "allow_cloud_analysis": allow_cloud,
                "store_screenshot": False,
                "created_at": datetime.now().isoformat(),
            }

        summary = analysis.get("summary", "Screen observed.")
        if not analysis.get("ok"):
            summary = f"Screen vision unavailable: {analysis.get('error') or 'analysis failed'}"
        return {
            "ok": bool(analysis.get("ok", True)),
            "summary": summary,
            "message": summary,
            "analysis": analysis,
            "request_id": request_id,
            "data": {
                "type": "screen_observation",
                "owner_vision": True,
                "requires_permission": False,
                "observation": {
                    "request_id": request_id,
                    "status": "completed" if analysis.get("ok") else "unavailable",
                    "summary": summary,
                    "detected_context": analysis.get("detected_context", "unknown"),
                    "screenshot_method": screenshot.get("method", "unknown"),
                    "source": analysis.get("source", ""),
                    "sensitive_content_detected": sensitive,
                    "store_screenshot": False,
                },
            },
        }

    def approve_observation(self, request_id, user_response, allow_cloud_analysis=False, store_screenshot=False):
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                return {"ok": False, "error": "Invalid request_id"}

            if EmergencyStop.is_engaged():
                return {"ok": False, "error": "Emergency stop is engaged"}

            pm_result = self._permission_manager.confirm("screen_capture", user_response)
            if pm_result["decision"] != "approved":
                return {
                    "ok": False,
                    "error": "Permission not granted for screen capture",
                    "permission_result": pm_result,
                }

            screenshot = self._screenshot_service.capture_real()
            if not screenshot.get("ok", True):
                request["status"] = "unavailable"
                request["screenshot_data"] = self._capture_metadata(screenshot)
                return {
                    "ok": False,
                    "request_id": request_id,
                    "status": "unavailable",
                    "error": screenshot.get("error") or "Screen capture unavailable",
                }
            privacy_result = self._privacy_guard.check_payload(screenshot)

            request["permission_granted"] = True
            request["allow_cloud_analysis"] = allow_cloud_analysis
            request["store_screenshot"] = store_screenshot
            request["screenshot_data"] = screenshot
            request["privacy_check"] = privacy_result
            request["status"] = "approved"

            return {
                "ok": True,
                "request_id": request_id,
                "status": "approved",
                "sensitive_content_detected": privacy_result["sensitive_content_detected"],
                "privacy_reason": privacy_result["reason"],
            }

    def cancel_observation(self, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                return {"ok": False, "error": "Invalid request_id"}
            request["status"] = "cancelled"
            return {"ok": True, "request_id": request_id, "status": "cancelled"}

    def analyze_observation(self, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                return {
                    "ok": False,
                    "summary": "No observation found with that ID",
                    "detected_context": "unknown",
                    "context_label": "Unknown Content",
                    "possible_issue": "",
                    "suggested_next_step": "",
                    "sensitive_content_detected": False,
                    "requires_confirmation_before_action": True,
                    "error": "Invalid request_id",
                }

            if request["status"] != "approved":
                return {
                    "ok": False,
                    "summary": "Observation is not in approved state",
                    "detected_context": "unknown",
                    "context_label": "Unknown Content",
                    "possible_issue": "",
                    "suggested_next_step": "",
                    "sensitive_content_detected": False,
                    "requires_confirmation_before_action": True,
                    "error": f"Observation status is '{request['status']}', expected 'approved'",
                }

            # Permission was granted; honour the cloud choice the user made at approval.
            analysis = self._vision_analyzer.analyze(
                request["screenshot_data"],
                allow_cloud=request.get("allow_cloud_analysis", False),
            )
            privacy = request.get("privacy_check", {})
            if privacy.get("sensitive_content_detected"):
                analysis["sensitive_content_detected"] = True
                analysis["possible_issue"] = privacy.get("reason", "Sensitive content detected")

            request["analysis_result"] = analysis
            request["status"] = "completed" if analysis.get("ok") else "unavailable"
            if not request.get("store_screenshot"):
                request["screenshot_data"] = self._capture_metadata(request["screenshot_data"])
            return analysis

    def get_observation_status(self, request_id):
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                return {"ok": False, "error": "Invalid request_id"}
            return {
                "ok": True,
                "request_id": request_id,
                "status": request["status"],
                "reason": request["reason"],
                "permission_granted": request["permission_granted"],
                "created_at": request["created_at"],
            }

    @property
    def screenshot_service(self):
        return self._screenshot_service

    @property
    def vision_analyzer(self):
        return self._vision_analyzer

    @property
    def permission_manager(self):
        return self._permission_manager

    @staticmethod
    def _capture_metadata(screenshot):
        return {
            key: value
            for key, value in dict(screenshot or {}).items()
            if key not in {"image_bytes", "visible_text"}
        }

    def reset(self):
        with self._lock:
            self._requests.clear()
            self._request_counter = 0
            self._screenshot_service = ScreenshotService()
            self._vision_analyzer = VisionAnalyzer()
            self._privacy_guard = PrivacyGuard()
            self._permission_manager = PermissionManager()
