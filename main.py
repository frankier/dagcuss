#!/usr/bin/env python2

from flask import (Flask, flash, redirect, request, render_template, url_for,
                   abort)
from flaskext.markdown import Markdown
app = Flask(__name__)
from settings import add_settings
add_settings(app)
#app.jinja_options = {'ignore_errors': False}
md = Markdown(app)

from dagcuss.forms import PostForm, RegistrationForm, LoginForm
from dagcuss.models import graph
from flaskext.login import (LoginManager, login_required, login_user,
                            logout_user)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.setup_app(app)


@login_manager.user_loader
def load_user(username):
    users = graph.users.index.lookup(username=username)
    try:
        return users.next()
    except StopIteration:
        return None


@app.route('/')
@app.route('/<int:post_id>/')
@app.route('/<int:post_id>/reply-page-<int:page_num>/')
def view_post(post_id=None, page_num=None):
    if post_id:
        post = graph.posts.get(post_id)
        # TODO: Bulbs should check correct model type returned, in fact Bulbs
        # should return a node and not a vertex
        if not post or post.element_type != "post":
            abort(404)
        if post.root:
            return redirect(url_for('view_post'))  # canonical url
    else:
        post = graph.posts.index.lookup(root=1).next()
    if page_num == 1:
        return redirect(url_for('view_post', post_id=post_id))
    if not page_num:
        page_num = 1
    return render_template('view_post.html', post=post, page_num=page_num)


@app.route('/add/', methods=["GET", "POST"])
@login_required
def add_post():
    form = PostForm()
    if form.validate_on_submit():
        post = graph.posts.create(title=form.title.data, body=form.body.data)
        for parent in form.parents.data:
            graph.replies.create(graph.posts.get(parent), post)
        return redirect(url_for("view_post", post_id=post.eid))
    return render_template("add_post.html", form=form)


@app.route("/register/", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        flash("Now just check your email to confirm your account and you can"
              "login.")
        graph.users.create(username=form.username.data,
                           password=form.password.data,
                           email=form.email.data,
                           active=0)
        # TODO: hash password
        return redirect(request.args.get("next") or url_for("view_post"))
    return render_template("register.html", form=form)


@app.route("/login/", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # login and validate the user...
        user = graph.users.index.get_unique(username=form.username.data,
                                            password=form.password.data)
        if not user:
            flash("No such username and password.")
            return render_template("login.html", form=form)
        login_user(user)
        flash("Logged in successfully.")
        return redirect(request.args.get("next") or url_for("view_post"))
    return render_template("login.html", form=form)


@app.route("/logout/")
#@login_required
def logout():
    logout_user()
    return redirect(url_for("view_post"))


@app.route("/about/")
def about():
    return render_template("about.html")


@app.route("/contact/")
def contact():
    return render_template("contact.html")


if __name__ == '__main__':
    app.run(
        debug=True
    )
