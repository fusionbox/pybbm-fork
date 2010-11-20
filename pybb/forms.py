import re
from datetime import datetime
import os.path

from django import forms
from django.utils.translation import ugettext as _
from annoying.functions import get_config

import settings

MEDIA_ROOT = get_config('MEDIA_ROOT', '/media/')

from pybb.models import Topic, Post, Profile, Attachment
from django.contrib.auth.models import User


class AddPostForm(forms.ModelForm):
    name = forms.CharField(label=_('Subject'))
    attachment = forms.FileField(label=_('Attachment'), required=False)

    class Meta(object):
        model = Post
        fields = ('body',)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.topic = kwargs.pop('topic', None)
        self.forum = kwargs.pop('forum', None)
        if not (self.topic or self.forum):
            raise ValueError('You should provide topic or forum')
        self.ip = kwargs.pop('ip', None)
        super(AddPostForm, self).__init__(*args, **kwargs)

        self.fields.keyOrder = ['name', 'body', 'attachment']

        if self.topic:
            self.fields['name'].widget = forms.HiddenInput()
            self.fields['name'].required = False

        if not settings.PYBB_ATTACHMENT_ENABLE:
            self.fields['attachment'].widget = forms.HiddenInput()
            self.fields['attachment'].required = False

    def clean_attachment(self):
        for f in self.files:
            if self.files[f].size > settings.PYBB_ATTACHMENT_SIZE_LIMIT:
                raise forms.ValidationError(_('Attachment is too big'))
        return self.cleaned_data['attachment']

    def save(self, *args, **kwargs):
        if self.forum:
            topic = Topic(forum=self.forum,
                          user=self.user,
                          name=self.cleaned_data['name'])
            topic.save()
        else:
            topic = self.topic
        post = Post(topic=topic, user=self.user, user_ip=self.ip,
                    markup=self.user.pybb_profile.markup,
                    body=self.cleaned_data['body'])
        post.save()
        if settings.PYBB_ATTACHMENT_ENABLE:
            for f in self.files:
                self.save_attachment(post, self.files[f])
        return post

    def save_attachment(self, post, memfile):
        if memfile:
            obj = Attachment(size=memfile.size, content_type=memfile.content_type,
                             name=memfile.name, post=post)
            dir = os.path.join(MEDIA_ROOT, settings.PYBB_ATTACHMENT_UPLOAD_TO)
            fname = '%d.0' % post.id
            path = os.path.join(dir, fname)
            file(path, 'w').write(memfile.read())
            obj.path = fname
            obj.save()


class AdminAddPostForm(AddPostForm):
    '''
    Superusers can post messages from any user and from any time
    If no user with specified name - new user will be created
    '''
    login = forms.CharField(label=_('User'))

    def __init__(self, *args, **kwargs):
        super(AdminAddPostForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder = ['name', 'login', 'body', 'attachment']

    def save(self, *args, **kwargs):
        try:
            self.user = User.objects.filter(username=self.cleaned_data['login']).get()
        except:
            self.user = User.objects.create_user(self.cleaned_data['login'],'%s@example.com' % self.cleaned_data['login'])
        return super(AdminAddPostForm, self).save(*args, **kwargs)




class EditProfileForm(forms.ModelForm):
    class Meta(object):
        model = Profile
        fields = ['signature', 'time_zone', 'language',
                  'show_signatures', 'markup']

    def clean_signature(self):
        value = self.cleaned_data['signature'].strip()
        if len(re.findall(r'\n', value)) > settings.PYBB_SIGNATURE_MAX_LINES:
            raise forms.ValidationError('Number of lines is limited to %d' % settings.PYBB_SIGNATURE_MAX_LINES)
        if len(value) > settings.PYBB_SIGNATURE_MAX_LENGTH:
            raise forms.ValidationError('Length of signature is limited to %d' % settings.PYBB_SIGNATURE_MAX_LENGTH)
        return value


class EditPostForm(forms.ModelForm):
    class Meta(object):
        model = Post
        fields = ['body']

    def save(self, commit=False):
        post = super(EditPostForm, self).save(commit=False)
        post.updated = datetime.now()
        post.save()
        return post


class EditHeadPostForm(EditPostForm):
    title = forms.CharField(label=_("Subject"), required=True)

    def __init__(self, *args, **kwargs):
        super(EditHeadPostForm, self).__init__(*args, **kwargs)
        self.fields.keyOrder = ['title', 'body']

    def save(self, commit=False):
        post = super(EditPostForm, self).save(commit=False)
        post.updated = datetime.now()
        post.save()

        post.topic.name = self.cleaned_data['title']
        post.topic.save()
        return post


class UserSearchForm(forms.Form):
    query = forms.CharField(required=False, label='')

    def filter(self, qs):
        if self.is_valid():
            query = self.cleaned_data['query']
            return qs.filter(username__contains=query)
        else:
            return qs
