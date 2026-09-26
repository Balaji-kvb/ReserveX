from flask import Flask, jsonify, request

app = Flask(__name__)

users = {}


@app.get("/health")
def health():
    return jsonify({
        "service": "user-service",
        "status": "healthy"
    })


@app.post("/users")
def create_user():
    data = request.get_json()

    user_id = len(users) + 1

    user = {
        "id": user_id,
        "name": data["name"],
        "email": data["email"]
    }

    users[user_id] = user

    return jsonify(user), 201


@app.get("/users/<int:user_id>")
def get_user(user_id):
    user = users.get(user_id)

    if user is None:
        return jsonify({
            "error": "User not found"
        }), 404

    return jsonify(user)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)