#!/usr/bin/env python3
"""
BBC Sports Football News Translator - Improved Version
Fetches RSS feed from BBC Sport and translates to Arabic
With retry logic and fallback APIs for better translation coverage
"""

import feedparser
import json
import os
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# Translation APIs
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"

def translate_with_mymemory(text):
    """Translate using MyMemory API"""
    try:
        params = {
            'q': text[:500],
            'langpair': 'en|ar'
        }
        response = requests.get(MYMEMORY_URL, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('responseStatus') == 200:
                return data['responseData']['translatedText']
    except Exception as e:
        print(f"MyMemory error: {e}")
    return None

def translate_with_google(text):
    """Translate using Google Translate API (unofficial)"""
    try:
        params = {
            'client': 'gtx',
            'sl': 'en',
            'tl': 'ar',
            'dt': 't',
            'q': text[:1000]
        }
        response = requests.get(GOOGLE_URL, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data and data[0]:
                translated = ''.join([item[0] for item in data[0] if item[0]])
                return translated
    except Exception as e:
        print(f"Google error: {e}")
    return None

def translate_text(text, retries=3, delay=1):
    """Translate with retry logic and fallback APIs"""
    if not text or text.strip() == "":
        return ""

    original_text = text
    last_error = None

    for attempt in range(retries):
        try:
            # Try MyMemory first (better Arabic support)
            result = translate_with_mymemory(text)
            if result and result != text and '<?xml' not in result:
                return result

            # Fallback to Google Translate
            result = translate_with_google(text)
            if result and result != text:
                return result

            # Small delay before retry
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(delay)

    # If all APIs fail, try with shorter text
    try:
        short_text = text[:200]
        result = translate_with_mymemory(short_text)
        if result:
            return result
    except:
        pass

    # Return original if all fail
    print(f"Warning: Could not translate text: {original_text[:50]}... (error: {last_error})")
    return original_text

def translate_batch(texts, max_workers=15):
    """Translate multiple texts in parallel with improved retry"""
    results = {}
    failed_indices = set()

    # First pass: try to translate all
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_text = {
            executor.submit(translate_text, text): idx
            for idx, text in enumerate(texts)
        }

        for future in as_completed(future_to_text):
            idx = future_to_text[future]
            try:
                result = future.result()
                if result and result.strip():
                    results[idx] = result
                else:
                    failed_indices.add(idx)
                    results[idx] = texts[idx]
            except Exception as e:
                print(f"Error translating text {idx}: {e}")
                failed_indices.add(idx)
                results[idx] = texts[idx]

    # Second pass: retry failed translations
    if failed_indices:
        print(f"Retrying {len(failed_indices)} failed translations...")
        time.sleep(2)  # Wait before retry

        for idx in failed_indices:
            result = translate_text(texts[idx], retries=5, delay=2)
            if result and result != texts[idx]:
                results[idx] = result
            else:
                results[idx] = texts[idx]

    return results

def fetch_rss_feed():
    """Fetch RSS feed from BBC Sport Football"""
    rss_url = "https://feeds.bbci.co.uk/sport/football/rss.xml"
    print(f"Fetching RSS feed from: {rss_url}")

    feed = feedparser.parse(rss_url)

    if not feed.entries:
        print("Warning: No entries found in feed")
        return []

    print(f"Found {len(feed.entries)} news items")
    return feed.entries

def clean_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ""
    import re
    clean = re.sub('<[^<]+?>', '', text)
    clean = clean.strip()
    return clean

def extract_image_url(entry):
    """Extract image URL from RSS entry"""
    # Try media:thumbnail (BBC uses this)
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            if 'url' in thumb:
                return thumb['url']

    # Try media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media and 'image' in media.get('type', ''):
                return media['url']

    # Try enclosure
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'url' in enclosure and 'image' in enclosure.get('type', ''):
                return enclosure['url']

    # Try links
    if hasattr(entry, 'links') and entry.links:
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return link['url']

    # Try image attribute
    if hasattr(entry, 'image') and entry.image:
        if isinstance(entry.image, dict) and 'href' in entry.image:
            return entry.image['href']
        elif isinstance(entry.image, str):
            return entry.image

    return None

def process_news_items(entries):
    """Process and translate news items"""
    print("Processing news items...")

    titles_en = []
    descriptions_en = []

    for entry in entries:
        titles_en.append(entry.get("title", ""))
        descriptions_en.append(clean_html(entry.get("description", "")))

    # Translate all titles in parallel
    print(f"Translating {len(titles_en)} titles...")
    title_translations = translate_batch(titles_en, max_workers=15)

    # Small delay between batches
    time.sleep(1)

    # Translate all descriptions in parallel
    print(f"Translating {len(descriptions_en)} descriptions...")
    description_translations = translate_batch(descriptions_en, max_workers=15)

    # Build final news items
    news_items = []
    translated_count = 0

    for idx, entry in enumerate(entries):
        image_url = extract_image_url(entry)
        title_ar = title_translations.get(idx, titles_en[idx])
        desc_ar = description_translations.get(idx, descriptions_en[idx])

        # Check if translation was successful
        title_translated = title_ar != titles_en[idx]
        desc_translated = desc_ar != descriptions_en[idx]

        item = {
            "title_en": titles_en[idx],
            "title_ar": title_ar,
            "description_en": descriptions_en[idx],
            "description_ar": desc_ar,
            "image_url": image_url,
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "fetched_at": datetime.utcnow().isoformat() + "Z"
        }
        news_items.append(item)

        if title_translated or desc_translated:
            translated_count += 1

        img_status = "[IMG]" if image_url else "[NO-IMG]"
        trans_status = "[OK]" if title_translated else "[FAIL]"
        print(f"  {idx+1}. {item['title_en'][:45]}... {img_status} {trans_status}")

    print(f"\nTranslation stats: {translated_count}/{len(news_items)} items fully translated")

    return news_items

def save_translated_news(news_items):
    """Save translated news to JSON file"""
    output_file = "translated_news.json"

    existing_news = []
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_news = json.load(f)
        except:
            existing_news = []

    # Deduplicate by link
    existing_links = {item['link'] for item in existing_news}
    new_items = [item for item in news_items if item['link'] not in existing_links]

    all_news = news_items + [n for n in existing_news if n['link'] not in {i['link'] for i in news_items}]
    all_news = all_news[:100]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)

    with_images = sum(1 for item in all_news if item.get('image_url'))
    print(f"\nSaved {len(all_news)} total news items ({len(new_items)} new, {with_images} with images)")

def main():
    start_time = datetime.now()
    print("=" * 60)
    print("BBC Sports Football News Translator (v3 - Improved)")
    print("=" * 60)

    entries = fetch_rss_feed()

    if entries:
        news_items = process_news_items(entries)
        save_translated_news(news_items)

        elapsed = (datetime.now() - start_time).total_seconds()
        print("=" * 60)
        print(f"Completed in {elapsed:.1f} seconds!")
        print("=" * 60)
    else:
        print("No news items to process")

if __name__ == "__main__":
    main()
