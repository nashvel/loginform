import requests

url = "http://localhost:8000/api/reset-password"
data = {
    "email": "nashvelbusiness@gmail.com",
    "code": "373597",
    "new_password": "password123"
}

response = requests.post(url, json=data)
print(response.json())  # Should print success or error details
