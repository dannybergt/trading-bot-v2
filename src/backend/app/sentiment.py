from textblob import TextBlob

def analyze_sentiment_basic(text: str) -> float:
    """
    Analyze sentiment using TextBlob (Basic).
    Returns a score between -1 (Negative) and 1 (Positive).
    """
    blob = TextBlob(text)
    return blob.sentiment.polarity

def analyze_news(news_items: list) -> list:
    """
    Analyze a list of news items.
    Each item should be a dict with 'title' and 'summary'.
    """
    results = []
    for item in news_items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        score = analyze_sentiment_basic(text)
        
        sentiment_label = 'neutral'
        if score > 0.1:
            sentiment_label = 'bullish'
        elif score < -0.1:
            sentiment_label = 'bearish'
            
        results.append({
            'title': item.get('title'),
            'summary': item.get('summary'),
            'score': score,
            'label': sentiment_label,
            'timestamp': item.get('providerPublishTime'),
            'url': item.get('url'),
            'source': item.get('source'),
        })
    return results
