import threading
from datetime import datetime

from src.orin.control.safety import EmergencyStop
from src.orin.control.permission_manager import PermissionManager
from src.orin.vision.screenshot_service import ScreenshotService
from src.orin.vision.vision_analyzer import VisionAnalyzer
from src.orin.vision.privacy_guard import PrivacyGuard


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

        screenshot = self._screenshot_service.capture()
        privacy_result = self._privacy_guard.check_payload(screenshot)

        request["screenshot_data"] = screenshot
        request["privacy_check"] = privacy_result

        analysis = self._vision_analyzer.analyze(screenshot)
        if privacy_result.get("sensitive_content_detected"):
            analysis["sensitive_content_detected"] = True
            analysis["possible_issue"] = privacy_result.get("reason", "Sensitive content detected")

        request["analysis_result"] = analysis
        request["status"] = "completed"

        return {
            "ok": True,
            "summary": analysis.get("summary", "Screen observed in trusted read-only mode."),
            "message": analysis.get("summary", "Screen observed in trusted read-only mode."),
            "analysis": analysis,
            "request_id": request_id,
            "data": {
                "type": "screen_observation",
                "requires_permission": False,
                "trusted_read_only": True,
                "observation": {
                    "request_id": request_id,
                    "status": "completed",
                    "summary": analysis.get("summary", ""),
                    "detected_context": analysis.get("detected_context", "unknown"),
                    "screenshot_method": screenshot.get("method", "unknown"),
                    "sensitive_content_detected": privacy_result.get("sensitive_content_detected", False),
                    "allow_cloud_analysis": False,
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

            screenshot = self._screenshot_service.capture()
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

            analysis = self._vision_analyzer.analyze(request["screenshot_data"])
            privacy = request.get("privacy_check", {})
            if privacy.get("sensitive_content_detected"):
                analysis["sensitive_content_detected"] = True
                analysis["possible_issue"] = privacy.get("reason", "Sensitive content detected")

            request["analysis_result"] = analysis
            request["status"] = "completed"
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

    def reset(self):
        with self._lock:
            self._requests.clear()
            self._request_counter = 0
            self._screenshot_service = ScreenshotService()
            self._vision_analyzer = VisionAnalyzer()
            self._privacy_guard = PrivacyGuard()
            self._permission_manager = PermissionManager()
