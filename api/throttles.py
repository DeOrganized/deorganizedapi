from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class StaffExemptUserThrottle(UserRateThrottle):
    """UserRateThrottle that lets staff/admin users through unconditionally."""

    def allow_request(self, request, view):
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return True
        return super().allow_request(request, view)


class StaffExemptAnonThrottle(AnonRateThrottle):
    """AnonRateThrottle that still exempts staff (e.g. during session-auth testing)."""

    def allow_request(self, request, view):
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return True
        return super().allow_request(request, view)
