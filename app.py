from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta

app = Flask(__name__)

app.config["SECRET_KEY"] = "change-this-secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    todos = db.relationship("Todo", backref="user", lazy=True)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default="General")
    priority = db.Column(db.String(10), default="Medium") 
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None

    user = User.query.get(uid)
    if not user:
        session.pop("user_id", None)
        return None

    return user

@app.context_processor
def inject_user():
    return {"user": get_current_user()}

def logged_in():
    return session.get("user_id") is not None

def parse_due_date():
    """HTML date input gives YYYY-MM-DD. Return python date or None."""
    due_str = (request.form.get("due_date") or "").strip()
    if not due_str:
        return None
    try:
        return datetime.strptime(due_str, "%Y-%m-%d").date()
    except ValueError:
        return None

@app.route("/")
def home():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))

    user = User.query.get(uid)
    if not user:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    todos = Todo.query.filter_by(user_id=user.id).order_by(Todo.created_at.desc()).all()
    todos_done = [t for t in todos if t.completed]
    todos_pending = [t for t in todos if not t.completed]

    total = len(todos)
    completed = len(todos_done)
    pending = len(todos_pending)

    percent_completed = round((completed / total) * 100) if total else 0
    percent_pending = round((pending / total) * 100) if total else 0
    percent_notstarted = max(0, 100 - percent_completed - percent_pending)

    return render_template(
        "index.html",
        todos_pending=todos_pending,
        todos_done=todos_done,
        percent_completed=percent_completed,
        percent_pending=percent_pending,
        percent_notstarted=percent_notstarted
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not name or not email or not password:
        flash("Please fill all fields.", "error")
        return render_template("register.html")

    if User.query.filter_by(email=email).first():
        flash("Email already registered. Please log in.", "error")
        return render_template("register.html")

    new_user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password)
    )
    db.session.add(new_user)
    db.session.commit()

    flash("Account created. Please log in.", "success")
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Please enter email and password.", "error")
        return render_template("login.html")

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("No account found for that email.", "error")
        return render_template("login.html")

    if not check_password_hash(user.password_hash, password):
        flash("Incorrect password.", "error")
        return render_template("login.html")

    session["user_id"] = user.id
    flash("Logged in successfully!", "success")
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.", "success")
    return redirect(url_for("login"))

@app.route("/todos")
def todos():
    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()
    q = (request.args.get("q") or "").strip()

    query = Todo.query.filter_by(user_id=user.id).order_by(Todo.created_at.desc())
    if q:
        query = query.filter(Todo.title.ilike(f"%{q}%"))

    todos = query.all()
    return render_template("todos.html", todos=todos, q=q)

@app.route("/todos/new", methods=["GET", "POST"])
def new_todo():
    if not logged_in():
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("todo_form.html", todo=None)

    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Task title cannot be empty.", "error")
        return render_template("todo_form.html", todo=None)

    category = request.form.get("category") or "General"
    priority = request.form.get("priority") or "Medium"
    due_date = parse_due_date()

    todo = Todo(
        title=title,
        user_id=get_current_user().id,
        category=category,
        priority=priority,
        due_date=due_date
    )

    db.session.add(todo)
    db.session.commit()

    flash("Task created!", "success")
    return redirect(url_for("todos"))

@app.route("/todos/<int:todo_id>/edit", methods=["GET", "POST"])
def edit_todo(todo_id):
    if not logged_in():
        return redirect(url_for("login"))

    todo = Todo.query.get_or_404(todo_id)
    
    if request.method == "GET":
        return render_template("todo_form.html", todo=todo)

    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Title cannot be empty.", "error")
        return render_template("todo_form.html", todo=todo)

    todo.title = title
    todo.category = request.form.get("category") or "General"
    todo.priority = request.form.get("priority") or "Medium"
    todo.due_date = parse_due_date()
    todo.completed = ("completed" in request.form)

    db.session.commit()

    flash("Task updated.", "success")
    return redirect(url_for("todos"))

@app.route("/todos/<int:todo_id>/delete")
def delete_todo(todo_id):
    if not logged_in():
        return redirect(url_for("login"))

    todo = Todo.query.get_or_404(todo_id)

    db.session.delete(todo)
    db.session.commit()

    flash("Task deleted.", "success")
    return redirect(url_for("todos"))

@app.route("/categories")
def categories():
    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()

    todos = Todo.query.filter_by(user_id=user.id).order_by(Todo.created_at.desc()).all()

    grouped = {}
    for t in todos:
        cat = t.category or "General"
        grouped.setdefault(cat, []).append(t)

    categories = sorted(grouped.keys())

    return render_template("categories.html", grouped=grouped, categories=categories)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if not logged_in():
        return redirect(url_for("login"))

    user = get_current_user()

    if request.method == "POST":
        new_name = (request.form.get("name") or "").strip()
        theme = request.form.get("theme") or "midnight"
        compact = request.form.get("compact") == "on"

        if new_name:
            user.name = new_name

        session["theme"] = theme
        session["compact"] = compact

        db.session.commit()
        flash("Settings saved!", "success")
        return redirect(url_for("settings"))

    current_theme = session.get("theme", "midnight")
    compact = session.get("compact", False)

    return render_template("settings.html", current_theme=current_theme, compact=compact)

if __name__ == "__main__":
    app.run(debug=True)
