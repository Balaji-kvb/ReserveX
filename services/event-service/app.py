from flask import Flask, jsonify, request

app = Flask(__name__)

events = {}


@app.get("/health")
def health():
    return jsonify({
        "service": "event-service",
        "status": "healthy"
    })


@app.post("/events")
def create_event():
    data = request.get_json()

    event_id = len(events) + 1

    event = {
        "id": event_id,
        "name": data["name"],
        "total_slots": data["total_slots"],
        "available_slots": data["total_slots"]
    }

    events[event_id] = event

    return jsonify(event), 201


@app.get("/events/<int:event_id>")
def get_event(event_id):
    event = events.get(event_id)

    if event is None:
        return jsonify({
            "error": "Event not found"
        }), 404

    return jsonify(event)


@app.get("/events/<int:event_id>/availability")
def get_availability(event_id):
    event = events.get(event_id)

    if event is None:
        return jsonify({
            "error": "Event not found"
        }), 404

    return jsonify({
        "event_id": event_id,
        "available_slots": event["available_slots"]
    })

@app.post("/events/<int:event_id>/reserve")
def reserve_slot(event_id):
    event = events.get(event_id)

    if event is None:
        return jsonify({
            "error": "Event not found"
        }), 404

    if event["available_slots"] <= 0:
        return jsonify({
            "error": "No slots available"
        }), 409

    event["available_slots"] -= 1

    return jsonify({
        "event_id": event_id,
        "available_slots": event["available_slots"],
        "message": "Slot reserved successfully"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
