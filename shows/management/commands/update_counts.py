from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from shows.models import Show
from users.models import Like, Comment


class Command(BaseCommand):
    help = 'Update like_count and comment_count for all shows'

    def handle(self, *args, **options):
        show_ct = ContentType.objects.get(app_label='shows', model='show')
        
        for show in Show.objects.all():
            show.like_count = Like.objects.filter(
                content_type=show_ct, 
                object_id=show.id
            ).count()
            show.comment_count = Comment.objects.filter(
                content_type=show_ct,
                object_id=show.id
            ).count()
            show.save(update_fields=['like_count', 'comment_count'])
            self.stdout.write(f"✅ {show.title}: {show.like_count} likes, {show.comment_count} comments")
        
        self.stdout.write(self.style.SUCCESS('✅ All counts updated!'))