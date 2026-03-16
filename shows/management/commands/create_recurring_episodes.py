from django.core.management.base import BaseCommand
from django.utils import timezone
from shows.models import Show, ShowEpisode
from datetime import datetime

class Command(BaseCommand):
    help = 'Automatically create future episodes for recurring shows'

    def handle(self, *args, **options):
        # 1. Get all recurring shows
        recurring_shows = Show.objects.filter(is_recurring=True, status='published')
        
        self.stdout.write(f"Found {recurring_shows.count()} recurring shows to process.")
        
        episodes_created = 0
        
        for show in recurring_shows:
            # 2. Find next 5 occurrences
            upcoming = show.get_upcoming_occurrences(count=5)
            
            if not upcoming:
                self.stdout.write(self.style.WARNING(f"Could not calculate upcoming occurrences for show: {show.title}"))
                continue
                
            for occurrence in upcoming:
                air_date = occurrence.date()
                
                # 3. Check if episode already exists for this date
                exists = ShowEpisode.objects.filter(show=show, air_date=air_date).exists()
                
                if not exists:
                    # Get the next episode number
                    last_episode = ShowEpisode.objects.filter(show=show).order_by('-episode_number').first()
                    next_number = (last_episode.episode_number + 1) if last_episode else 1
                    
                    # Create the episode
                    ShowEpisode.objects.create(
                        show=show,
                        episode_number=next_number,
                        title=f"Episode {next_number}",
                        description=f"Automated episode for {show.title}",
                        air_date=air_date,
                        is_premium=False # Default to free
                    )
                    
                    episodes_created += 1
                    self.stdout.write(self.style.SUCCESS(f"Created Episode {next_number} for '{show.title}' on {air_date}"))
                else:
                    self.stdout.write(f"Episode already exists for '{show.title}' on {air_date}")

        self.stdout.write(self.style.SUCCESS(f"Successfully processed recurring shows. {episodes_created} new episodes created."))
