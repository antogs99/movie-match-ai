
import urllib.request
import json

# Set your API key here
api_key = 'txE5mRj2xQgglNhIrdrAwzjznEufBHXKru7MeTuT'
url = f'https://api.watchmode.com/v1/sources/?apiKey={api_key}'

with urllib.request.urlopen(url) as response:
    data = json.loads(response.read().decode())
    print(data)