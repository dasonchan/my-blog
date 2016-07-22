import os
import re
import random
import hashlib
import hmac
import time

from string import letters

import webapp2
import jinja2

from google.appengine.ext import ndb

from user import *
from post import *

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)

# handlers for all pages


class BlogHandler(webapp2.RequestHandler):

    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        user_val = make_secure_val(str(user.name))
        self.response.headers.add_header(
            "Set-Cookie", "user=%s; Path=/" % user_val)

    def logout(self):
        self.response.headers.add_header("Set-Cookie", "user=; Path=/")

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        username = self.read_secure_cookie('user')
        self.user = User.gql("where name = '%s'" % username).get()


class MainPage(BlogHandler):

    def get(self):
        self.render("index.html")


class BlogFront(BlogHandler):

    """Renders the blog front page"""

    def get(self):
        posts = Post.gql("order by created desc limit 10")
        self.render('front.html', posts=posts)


class PostPage(BlogHandler):

    """Renders the page of a single post and its comments and likes"""

    def get(self, post_id):
        key = ndb.Key('Post', int(post_id), parent=blog_key())
        p = key.get()
        comments = Comment.gql(
            "where post_id = %s order by created desc" % (post_id))
        liked = None

        if self.user:
            liked = Like.gql(
                "where post_id = :1 AND author.name = :2", int(post_id), self.user.name).get()
        if not p:
            self.render("404.html")
            return

        self.render("post.html", p=p, comments=comments, liked=liked)

    def post(self, post_id):
        key = ndb.Key('Post', int(post_id), parent=blog_key())
        p = key.get()

        if not self.user:
            return self.redirect('/login')
        else:
            liked = Like.gql(
                "WHERE post_id = :1 AND author.name = :2", int(post_id), self.user.name).get()
            if self.request.get("like"):
                # User liked post
                if self.user.name != p.author.name and not liked:
                    # Make sure user is not the post author and has not liked the post
                    p.likes += 1
                    like = Like(post_id=int(post_id), author=self.user)
                    like.put()
                    p.put()
                    time.sleep(0.2)
                self.redirect("/blog/%s" % post_id)
            elif self.request.get("unlike"):
                # User unliked post
                if self.user.name != p.author.name and liked:
                    # Make sure user is not the post author and has liked the post
                    p.likes -= 1
                    key = liked.key
                    key.delete()
                    p.put()
                    time.sleep(0.2)
                self.redirect("/blog/%s" % post_id)
            else:
                # User commented on post
                content = self.request.get("content")
                if content:
                    comment = Comment(
                        content=str(content), author=self.user, post_id=int(post_id))
                    comment.put()
                    time.sleep(0.1)
                    self.redirect("/blog/%s" % post_id)
                else:
                    self.render("post.html", p=p)


class NewPost(BlogHandler):

    """Handles process of generating new posts"""

    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        # only registerd users can write posts
        if not self.user:
            return self.redirect('/login')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent=blog_key(), subject=subject,
                     content=content, author=self.user)
            p.put()
            self.redirect('/blog/%s' % str(p.key.id()))
        else:
            error = "subject and content please!"
            self.render(
                "newpost.html", subject=subject, content=content, error=error)


class Signup(BlogHandler):

    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username,
                      email=self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Register(Signup):

    def done(self):
        # make sure the user doesn't already exist
        u = User.by_name(self.username)
        username = self.request.get("username")
        password = self.request.get("password")
        verify = self.request.get("verify")
        email = self.request.get("email")

        if u:
            msg = 'That user already exists.'
            self.render(
                'signup-form.html', error_username=msg, username=username, email=email)
        else:
            u = User(name=username, pw_hash=make_pw_hash(
                username, password), email=email)
            u.put()

            user_cookie = make_secure_val(str(self.username))
            self.response.headers.add_header(
                'Set-Cookie', 'user_id=%s; Path=/' % user_cookie)
            time.sleep(0.1)
            self.redirect('/blog')


class Login(BlogHandler):

    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error=msg)


class Logout(BlogHandler):

    def get(self):
        self.logout()
        self.redirect('/blog')


class EditPost(BlogHandler):

    """Handles editing of posts"""

    def get(self):
        if self.user:
            post_id = self.request.get("post")
            key = ndb.Key('Post', int(post_id), parent=blog_key())
            p = key.get()
            if not p:
                self.render("404.html")
                return
            self.render("editpost.html", subject=p.subject, content=p.content)
        else:
            self.redirect("/login")

    def post(self):
        if self.user:
            post_id = self.request.get("post")
            key = ndb.Key('Post', int(post_id), parent=blog_key())
            p = key.get()

            if p and p.author.name == self.user.name:
                subject = self.request.get("subject")
                content = self.request.get("content")
                if subject and content:
                    p.subject = subject
                    p.content = content
                    p.put()
                    time.sleep(0.1)
                    self.redirect("/blog")
                else:
                    error = "subject and content please!"
                    self.render(
                        "editpost.html", subject=subject, content=content, error=error)

            else:
                self.error(401)
                self.render("401.html")
        else:

            self.redirect('/login')


class DeletePost(BlogHandler):

    """Handles deletion of blog posts"""

    def get(self):
        if self.user:
            post_id = self.request.get("post")
            key = ndb.Key('Post', int(post_id), parent=blog_key())
            p = key.get()
            if not p:
                self.render("404.html")
                return
            self.render("deletepost.html", p=p)
        else:
            self.redirect("/login")

    def post(self):
        if self.user:
            post_id = self.request.get("post")
            key = ndb.Key('Post', int(post_id), parent=blog_key())
            p = key.get()
            if p and p.author.name == self.user.name:
                key.delete()
                time.sleep(0.1)
            self.redirect("/blog")
        else:
            self.redirect("/login")


class EditComment(BlogHandler):

    """Handles editing of comments"""

    def get(self):
        if self.user:
            comment_id = self.request.get("comment")
            key = ndb.Key('Comment', int(comment_id))
            comment = key.get()
            if not comment:
                self.render("404.html")
                return
            self.render(
                "editcomment.html", content=comment.content, post_id=comment.post_id)
        else:
            self.redirect("/login")

    def post(self):
        if self.user:
            comment_id = self.request.get("comment")
            key = ndb.Key('Comment', int(comment_id))
            comment = key.get()
            if comment and comment.author.name == self.user.name:
                content = self.request.get("content")
                if content:
                    comment.content = content
                    comment.put()
                    time.sleep(0.1)
                    self.redirect("/blog/%s" % int(comment.post_id))
                else:
                    error = "Subject and content please!"
                    self.render("editcomment.html",
                                content=comment.content,
                                post_id=comment.post_id,
                                error=error)
            else:
                self.redirect("/blog/%s" % int(commnet.post_id))
        else:
            self.redirect("/login")


class DeleteComment(BlogHandler):

    """Handles deletion of comments"""

    def get(self):
        if self.user:
            comment_id = self.request.get("comment")
            key = ndb.Key('Comment', int(comment_id))
            comment = key.get()
            if not comment:
                self.render("404.html")
                return
            self.render("deletecomment.html", comment=comment)
        else:
            self.redirect("/login")

    def post(self):
        if self.user:
            comment_id = self.request.get("comment")
            key = ndb.Key('Comment', int(comment_id))
            comment = key.get()
            if comment and comment.author.name == self.user.name:
                post_id = comment.post_id
                key.delete()
                time.sleep(0.1)
            self.redirect("/blog/%s" % int(post_id))
        else:
            self.redirect("/login")


class Welcome(BlogHandler):

    def get(self):
        if self.user:
            self.render('welcome.html', username=self.user.name)
        else:
            self.redirect('/signup')

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/welcome', Welcome),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/edit', EditPost),
                               ('/blog/delete', DeletePost),
                               ('/comment/edit', EditComment),
                               ('/comment/delete', DeleteComment)
                               ],
                              debug=True)
