import os
import re
import random
import hashlib
import hmac

import webapp2
import jinja2

from user import *

from google.appengine.ext import ndb


def blog_key(name='default'):
    """Assigns a key to each post"""
    return ndb.Key('blogs', name)


class Post(ndb.Model):
    """define a blog post"""
    subject = ndb.StringProperty(required=True)
    content = ndb.TextProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    author = ndb.StructuredProperty(User)
    likes = ndb.IntegerProperty(default=0)
    last_modified = ndb.DateTimeProperty(auto_now=True)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p=self)


class Comment(ndb.Model):
    """define a comment"""
    post_id = ndb.IntegerProperty(required=True)
    author = ndb.StructuredProperty(User)
    content = ndb.StringProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)


class Like(ndb.Model):
    """define a like on a post"""
    post_id = ndb.IntegerProperty(required=True)
    author = ndb.StructuredProperty(User)
