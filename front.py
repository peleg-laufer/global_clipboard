import requests

BASE_URL = "http://localhost:8000"

def main():
    print("=== FastAPI Frontend ===\n")
    
    # Test root endpoint
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"GET /: {response.json()}\n")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to FastAPI server. Make sure it's running on http://localhost:8000\n")
        return
    
    # Test items endpoint
    item_id = 42
    q = "test"
    response = requests.get(f"{BASE_URL}/items/{item_id}", params={"q": q})
    print(f"GET /items/{item_id}?q={q}: {response.json()}\n")

if __name__ == "__main__":
    main()