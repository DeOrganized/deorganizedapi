from rest_framework import permissions


class IsCreatorRole(permissions.BasePermission):
    """
    Permission to only allow users with 'creator' role.
    """
    message = "Only users with Creator role can perform this action."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'creator'
        )


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to the owner
        # Handle different owner field names
        if hasattr(obj, 'creator'):
            return obj.creator == request.user
        elif hasattr(obj, 'author'):
            return obj.author == request.user
        elif hasattr(obj, 'organizer'):
            return obj.organizer == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False


class IsCreatorOrReadOnly(permissions.BasePermission):
    """
    Allow creators to create, allow owners to edit/delete, read-only for others.
    """
    def has_permission(self, request, view):
        # Read permissions for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Create permissions only for creators
        if request.method == 'POST':
            return (
                request.user and 
                request.user.is_authenticated and 
                request.user.role == 'creator'
            )
        
        # Edit/Delete handled by object permission
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Edit/Delete only for owner
        # Check direct creator
        if hasattr(obj, 'creator'):
            return obj.creator == request.user
        
        # Check show creator for episodes
        if hasattr(obj, 'show') and hasattr(obj.show, 'creator'):
            return obj.show.creator == request.user
            
        return False


class IsAuthenticatedOrReadOnly(permissions.BasePermission):
    """
    Allow authenticated users to create/edit, read-only for anonymous.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated
