from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Community, Membership, CommunityFollow

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'profile_picture', 'is_verified']
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'user', 'community', 'role', 'joined_at']
        read_only_fields = ['id', 'user', 'community', 'joined_at']


class CommunitySerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    founder = serializers.SerializerMethodField()
    user_membership = serializers.SerializerMethodField()
    user_is_following = serializers.SerializerMethodField()

    def get_member_count(self, obj):
        # Prefer queryset annotation (list views), fall back to property
        return getattr(obj, 'member_count_annotated', obj.member_count)

    def get_founder(self, obj):
        # Prefer prefetched founder_memberships (retrieve/list), else single query
        if hasattr(obj, 'founder_memberships') and obj.founder_memberships:
            return UserSummarySerializer(obj.founder_memberships[0].user).data
        membership = obj.memberships.filter(role='founder').select_related('user').first()
        if membership:
            return UserSummarySerializer(membership.user).data
        return UserSummarySerializer(obj.created_by).data

    def get_user_membership(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            membership = Membership.objects.get(user=request.user, community=obj)
            return {'id': membership.id, 'role': membership.role, 'joined_at': membership.joined_at}
        except Membership.DoesNotExist:
            return None

    def get_user_is_following(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return CommunityFollow.objects.filter(user=request.user, community=obj).exists()

    class Meta:
        model = Community
        fields = [
            'id', 'name', 'slug', 'description', 'avatar', 'banner',
            'tier', 'website', 'twitter', 'agent_api_url',
            'created_by', 'created_at', 'updated_at',
            'member_count', 'founder', 'user_membership', 'user_is_following',
        ]
        read_only_fields = ['id', 'slug', 'created_by', 'created_at', 'updated_at']


class CommunityCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Community
        fields = ['name', 'description', 'avatar', 'banner', 'tier', 'website', 'twitter', 'agent_api_url']


class AdminCommunitySerializer(CommunitySerializer):
    """Extended serializer for staff admin views — adds post/show/event counts."""
    post_count = serializers.SerializerMethodField()
    show_count = serializers.SerializerMethodField()

    def get_post_count(self, obj):
        return getattr(obj, 'post_count_annotated', 0)

    def get_show_count(self, obj):
        return getattr(obj, 'show_count_annotated', 0)

    # Skip per-request user queries — not relevant in admin context
    def get_user_membership(self, obj):
        return None

    def get_user_is_following(self, obj):
        return False

    class Meta(CommunitySerializer.Meta):
        fields = CommunitySerializer.Meta.fields + ['post_count', 'show_count']


class MembershipWithCommunitySerializer(serializers.ModelSerializer):
    """Used by my_communities — full nested community object."""
    community = serializers.SerializerMethodField()

    def get_community(self, obj):
        return CommunitySerializer(obj.community, context=self.context).data

    class Meta:
        model = Membership
        fields = ['id', 'role', 'joined_at', 'community']
        read_only_fields = fields
