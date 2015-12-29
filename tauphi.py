from __future__ import unicode_literals

import sys
import json
from datetime import date, timedelta
from urlparse import urlparse

import tweepy
from pyatom import AtomFeed
import boto


def get_config():
    try:
        with open('tauphi_config.json') as handle:
            return json.load(handle)

    except (IOError, ValueError) as e:
        print('Error loading tauphi_config.json: {}'.format(e))
        sys.exit(1)


def get_api(config, **kwargs):
    auth = tweepy.OAuthHandler(config['api_key'], config['api_secret'])
    auth.set_access_token(config['access_token'], config['access_token_secret'])
    return tweepy.API(auth, **kwargs)


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.gif', '.png'}


def timeline_to_feed(config):
    api = get_api(config, cache=tweepy.FileCache('.cache', timeout=60 * 5))
    me = api.me()

    feed = AtomFeed(
        title=config.get(
            'feed_title',
            'Links from the timeline of @{}'.format(me.screen_name)
        ),
        url='https://twitter.com/{}'.format(me.screen_name),
        feed_url=config.get('feed_url'),
        generator=('Tauphi', 'https://github.com/tgecho/tauphi', None),
    )

    assert config.get('max_items') or config.get('max_days'), 'Please specify at least one of max_items or max_days.'

    item_count = 0
    min_date = date.today() - timedelta(days=config['max_days']) if config.get('max_days') else None

    for tweet in tweepy.Cursor(api.home_timeline, count=200).items():
        if tweet.entities.get('urls'):
            author = tweet.author

            item_count += 1

            if config.get('max_items') and item_count > config.get('max_items'):
                break

            if min_date and tweet.created_at.date() < min_date:
                break

            title = '@{}: {}'.format(author.screen_name, tweet.text)
            content = tweet.text

            for url in tweet.entities['urls']:
                expanded = url['expanded_url']
                display = url['display_url']

                title = title.replace(url['url'], display)

                link = '<a href="{}" title="{}">{}</a>'.format(
                    url['url'], expanded, display,
                )
                content = content.replace(url['url'], link)

                if any(expanded.endswith(e) for e in IMAGE_EXTENSIONS):
                    content += '<p><img src="{}" /></p>'.format(expanded)

            if getattr(tweet, 'extended_entities', None):
                for embed in tweet.extended_entities['media']:
                    if embed == 'photo':
                        content += '<p><img src="{}" /></p>'.format(
                            embed.media_url_https)

            tweet_url = 'https://twitter.com/{}/status/{}'.format(
                tweet.author.screen_name, tweet.id_str)

            feed.add(
                title=title,
                content=content,
                content_type='html',
                author='{} (@{})'.format(author.name, author.screen_name),
                url=tweet_url,
                published=tweet.created_at,
                updated=tweet.created_at,
                links=[{'href': u['url']} for u in tweet.entities['urls']]
            )

    return unicode(feed)


def upload_feed(config, feed):
    conn = boto.connect_s3()
    bucket_name, feed_path = urlparse(config['feed_url']).path.strip('/').split('/', 1)
    bucket = conn.get_bucket(bucket_name)
    key = bucket.new_key(feed_path)
    key.set_contents_from_string(feed)
    key.content_type = 'application/atom+xml'
    key.set_acl('public-read')


if __name__ == '__main__':
    config = get_config()
    feed = timeline_to_feed(config)
    upload_feed(config, feed)