from flask import Blueprint, render_template, request

exercise_builder_bp = Blueprint('exercise_builder', __name__)

# Preset exercise data
EXERCISES = [
    {
        "id": "squats",
        "name": "Squats",
        "vietnamese": "Ngồi xổm",
        "reps": 12,
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/8pRbNUW.gif",
    },
    {
        "id": "glute_bridge",
        "name": "Glute Bridge",
        "vietnamese": "Cầu mông",
        "reps": 15,
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/Uf29ky7.gif",
    },
    {
        "id": "heel_raises",
        "name": "Heel Raises",
        "vietnamese": "Nâng gót chân",
        "reps": 15,
        "sets": 3,
        "frequency": "Daily",
        "img_url": "https://i.imgur.com/t5v9Pqv.gif",
    },
    {
        "id": "wall_slides",
        "name": "Wall Slides",
        "vietnamese": "Trượt tường",
        "reps": 12,
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/9j4jpjq.gif",
    },
    {
        "id": "clamshells",
        "name": "Clamshells",
        "vietnamese": "Động tác sò",
        "reps": 15,
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/yb3VK3O.gif",
    },
    {
        "id": "bird_dog",
        "name": "Bird Dog",
        "vietnamese": "Động tác chim chó",
        "reps": 10,
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/7wR4KfL.gif",
    },
    {
        "id": "side_plank",
        "name": "Side Plank",
        "vietnamese": "Plank nghiêng",
        "reps": "Hold 20s",
        "sets": 3,
        "frequency": "3 times per week",
        "img_url": "https://i.imgur.com/m2ku6RQ.gif",
    },
]

@exercise_builder_bp.route('/exercise_builder', methods=['GET', 'POST'])
def exercise_builder():
    if request.method == 'POST':
        selected_ids = request.form.getlist('exercises')
        if len(selected_ids) == 0:
            error = "Please select at least one exercise."
            return render_template('exercise_builder.html', exercises=EXERCISES, error=error)
        if len(selected_ids) > 7:
            error = "Please select no more than 7 exercises."
            return render_template('exercise_builder.html', exercises=EXERCISES, error=error)
        selected_exercises = [ex for ex in EXERCISES if ex["id"] in selected_ids]
        return render_template('exercise_results.html', selected=selected_exercises)
    # On GET, just render the builder
    return render_template('exercise_builder.html', exercises=EXERCISES)

# Example if you ever want to redirect inside this blueprint:
# from flask import redirect, url_for
# return redirect(url_for('exercise_builder.exercise_builder'))
