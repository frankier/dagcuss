from flaskext.wtf import BooleanField, TextField, TextAreaField, PasswordField, RecaptchaField, SelectMultipleField, IntegerField
from flaskext.wtf import validators, Form, ValidationError
from dagcuss.models import graph

class PostForm(Form):
    title = TextField('Title', [validators.Optional()], description="100% optional")
    body = TextAreaField('Body', [validators.Required()])
    parents = SelectMultipleField('Parents', choices=[(unicode(post.eid), unicode(post)) for post in graph.posts.index.lookup(element_type="post")])
    # TODO: make custom field since choices is currently kept in memory

    def validate_parents(form, field):
        if len(field.data) > 3:
            raise ValidationError("You must reply to three or less posts.")
        if len(field.data) < 1:
            raise ValidationError("You must reply to at least one post.")
        parents = [graph.posts.get(parent) for parent in field.data]
        for parent in parents:
            ancestor = parent.has_ancestor_any([other_parent for other_parent in parents if parent != other_parent])
            if ancestor:
                raise ValidationError("%s is an ancestor of %s." % (ancestor, parent))


class RegistrationForm(Form):
    username = TextField('Username', [validators.Required(), validators.Length(min=4, max=25)])
    password = PasswordField('Password', [validators.Required(), validators.EqualTo('confirm', message='Passwords must match')])
    confirm = PasswordField('Confirm Password', [validators.Required()])
    accept_tos = BooleanField('I accept the TOS', [validators.Required()])
    recaptcha = RecaptchaField()


class LoginForm(Form):
    username = TextField('Username', [validators.Required()])
    password = PasswordField('Password', [validators.Required()])
