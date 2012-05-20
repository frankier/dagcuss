import time

from flask import (flash, redirect, request, render_template, url_for, abort,
                   jsonify)
from flaskext.markdown import Markdown
from flaskext.login import (LoginManager, login_required, login_user,
                            logout_user)
from flask_debugtoolbar import DebugToolbarExtension

from dagcuss import app
from dagcuss.forms import PostForm, RegistrationForm, LoginForm
from dagcuss.models import graph, element_to_model, Reply
from dagcuss import dynagraph

toolbar = DebugToolbarExtension(app)
md = Markdown(app)
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


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.context_processor
def utility_processor():
    from collections import defaultdict
    url_for_map = defaultdict(lambda: [])
    for rule in app.url_map.iter_rules():
        param_count = len([param for param in rule._trace if param[0]])
        bits = []
        add = bits.append
        for is_dynamic, data in rule._trace: # begins with underscore == naughty
            if is_dynamic:
                add('{{ %s }}' % (data,))
            else:
                add(data)
        url_for_map[rule.endpoint].append((param_count, ''.join(bits).split('|', 1)[1]))
    for endpoint in url_for_map:
        url_for_map[endpoint] = [template for _, template in sorted(url_for_map[endpoint], reverse=True)]
    return {
        'url_for_data': url_for_map
    }


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


@login_required
@app.route('/add/', methods=["GET", "POST"])
def add_post():
    form = PostForm()
    form.parents.choices = [(unicode(post.eid), unicode(post))
                            for post in graph.posts.get_all()]
    if form.validate_on_submit():
        post = graph.posts.create(
            title=form.title.data,
            body=form.body.data,
            parents=[graph.posts.get(parent) for parent in form.parents.data]
        )
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
        print "logged in sucessfully"
        return redirect(request.args.get("next") or url_for("view_post"))
    return render_template("login.html", form=form)


#@login_required
@app.route("/logout/")
def logout():
    logout_user()
    return redirect(url_for("view_post"))


@app.route("/about/")
def about():
    return render_template("about.html")


@app.route("/contact/")
def contact():
    return render_template("contact.html")


@app.route("/api/by-tile/")
def by_tile():
    #import sys, hotshot
    #prof = hotshot.Profile('tile-profile.log')
    #prof.start()
    posts = set()
    replies = set()
    tile_xs = request.args.getlist('tile_x', type=int)
    tile_ys = request.args.getlist('tile_y', type=int)
    tiles = zip(tile_xs, tile_ys)
    if len(tile_xs) != len(tile_ys) or len(tile_xs) == 0:
        abort(400)
    for post in graph.posts.get_all(): # XXX: Bad, use an index
        for tile in tiles:
            if post.tile_x == tile[0] and post.tile_y == tile[1]:
                posts.add(post)
                for reply in post.inE("reply"):
                    replies.add(element_to_model(reply, Reply))
                for reply in post.outE("reply"):
                    replies.add(element_to_model(reply, Reply))
    result = jsonify(
        posts=[{
            'id': post.eid,
            'root': post.root,
            'title': post.title,
            'x': post.x,
            'y': post.y,
            'at': time.mktime(post.at.timetuple()),
            'parents': [parent.eid for parent in post.inE("reply")],
            'children': [child.eid for child in post.outE("reply")],
        } for post in posts],
        replies=[{
            'id': reply.eid,
            'pos': reply.pos if reply.pos else [], # XXX: From, to
            'in_id': reply.inV().eid,
            'out_id': reply.outV().eid,
        } for reply in replies]
    )
    #prof.stop()
    return result


@app.route("/api/post-detail/<int:post_id>/")
def get_post_detail(post_id): 
    post = graph.posts.get(post_id)
    extra_post_ids = set(request.args.getlist('extra_posts', type=int))
    extra_posts = []
    for extra_post_id in extra_post_ids:
        extra_post = graph.posts.get(extra_post_id)
        if extra_post:
            extra_posts.append(extra_post)
    if not post or post.element_type != "post":
        abort(404)
    return jsonify(
        posts=[{
            'id': post.eid,
            'body': post.body,
        }] + [{
            'id': extra_post.eid,
            'title': extra_post.title,
            'at': time.mktime(extra_post.at.timetuple()),
        } for extra_post in extra_posts]
    )
