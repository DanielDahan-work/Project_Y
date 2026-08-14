from app import create_app

app = create_app()
client = app.test_client()

with client.session_transaction() as session:
    print("BEFORE:", dict(session))

response = client.post(
    "/login",
    data={
        "username": "daniel",
        "password": "Test1234"
    },
    follow_redirects=False
)

print("STATUS:", response.status_code)
print("LOCATION:", response.headers.get("Location"))
print("SET-COOKIE:", response.headers.get("Set-Cookie"))

with client.session_transaction() as session:
    print("AFTER:", dict(session))
