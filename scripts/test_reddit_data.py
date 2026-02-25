#cd /Volumes/server-ssd/skills/skill-last30days/scripts && python3 -c "
from lib import ollama_reddit

# Test global search for 'infoproducts'
items = ollama_reddit.search_reddit_global('infoproducts', limit=10, sort='new')

print(f'✓ Global Reddit search for \"infoproducts\"')
print(f'✓ Found {len(items)} posts across multiple subreddits')
print()

# Group by subreddit to show diversity
from collections import Counter
subreddits = [item['subreddit'] for item in items]
subreddit_counts = Counter(subreddits)

print('Posts by subreddit:')
for sub, count in subreddit_counts.most_common():
    print(f'  r/{sub}: {count} posts')
print()

print('Sample results:')
for i, item in enumerate(items[:5], 1):
    print(f'{i}. [{item["subreddit"]}] {item["title"][:60]}...')
    print(f'   Date: {item["date"]}')
