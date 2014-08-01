# -*- coding: utf-8 -*-
import re
from django.core.cache import get_cache
from django.views.generic.base import TemplateResponseMixin
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import resolve
from django.shortcuts import redirect
from django.utils.encoding import force_text


class SetHeadlineMixin(object):

    """
    Mixin allows you to set a static headline through a static property on the
    class or programmatically by overloading the get_headline method.
    """
    headline = None  # Default the headline to none

    def get_context_data(self, **kwargs):
        kwargs = super(SetHeadlineMixin, self).get_context_data(**kwargs)
        # Update the existing context dict with the provided headline.
        kwargs.update({"headline": self.get_headline()})
        return kwargs

    def get_headline(self):
        if self.headline is None:  # If no headline was provided as a view
                                   # attribute and this method wasn't
                                   # overridden raise a configuration error.
            raise ImproperlyConfigured(
                '{0} is missing a headline. '
                'Define {0}.headline, or override '
                '{0}.get_headline().'.format(self.__class__.__name__))
        return force_text(self.headline)


class StaticContextMixin(object):

    """
    Mixin allows you to set static context through a static property on
    the class.
    """
    static_context = None

    def get_context_data(self, **kwargs):
        kwargs = super(StaticContextMixin, self).get_context_data(**kwargs)

        try:
            kwargs.update(self.get_static_context())
        except (TypeError, ValueError):
            raise ImproperlyConfigured(
                '{0}.static_context must be a dictionary or container '
                'of two-tuples.'.format(self.__class__.__name__))
        else:
            return kwargs

    def get_static_context(self):
        if self.static_context is None:
            raise ImproperlyConfigured(
                '{0} is missing the static_context property. Define '
                '{0}.static_context, or override '
                '{0}.get_static_context()'.format(self.__class__.__name__)
            )
        return self.static_context


class CanonicalSlugDetailMixin(object):

    """
    A mixin that enforces a canonical slug in the url.

    If a urlpattern takes a object's pk and slug as arguments and the slug url
    argument does not equal the object's canonical slug, this mixin will
    redirect to the url containing the canonical slug.
    """

    def dispatch(self, request, *args, **kwargs):
        # Set up since we need to super() later instead of earlier.
        self.request = request
        self.args = args
        self.kwargs = kwargs

        # Get the current object, url slug, and
        # urlpattern name (namespace aware).
        obj = self.get_object()
        slug = self.kwargs.get(self.slug_url_kwarg, None)
        match = resolve(request.path_info)
        url_parts = match.namespaces
        url_parts.append(match.url_name)
        current_urlpattern = ":".join(url_parts)

        # Figure out what the slug is supposed to be.
        if hasattr(obj, "get_canonical_slug"):
            canonical_slug = obj.get_canonical_slug()
        else:
            canonical_slug = self.get_canonical_slug()

        # If there's a discrepancy between the slug in the url and the
        # canonical slug, redirect to the canonical slug.
        if canonical_slug != slug:
            params = {self.pk_url_kwarg: obj.pk,
                      self.slug_url_kwarg: canonical_slug,
                      'permanent': True}
            return redirect(current_urlpattern, **params)

        return super(CanonicalSlugDetailMixin, self).dispatch(
            request, *args, **kwargs)

    def get_canonical_slug(self):
        """
        Override this method to customize what slug should be considered
        canonical.

        Alternatively, define the get_canonical_slug method on this view's
        object class. In that case, this method will never be called.
        """
        return self.get_object().slug


class AllVerbsMixin(object):

    """Call a single method for all HTTP verbs.

    The name of the method should be specified using the class attribute
    ``all_handler``. The default value of this attribute is 'all'.
    """
    all_handler = 'all'

    def dispatch(self, request, *args, **kwargs):
        if not self.all_handler:
            raise ImproperlyConfigured(
                '{0} requires the all_handler attribute to be set.'.format(
                    self.__class__.__name__))

        handler = getattr(self, self.all_handler, self.http_method_not_allowed)
        return handler(request, *args, **kwargs)


class CacheMixin(TemplateResponseMixin):
    cache_timeout = 600

    def get_cache_timeout(self):
        if isinstance(self.cache_timeout, int):
            return self.cache_timeout
        match = re.match(r"(?P<count>\d+)(?P<time>[dhm])", self.cache_timeout)
        count = match.group("count")
        time = match.group("time")
        if time == "m":
            seconds = 60
        elif time == "h":
            seconds = 3600
        elif time == "d":
            seconds = 86400
        return seconds * int(count)

    def render_to_response(self, context, **response_kwargs):
        response = super(CacheMixin, self).render_to_response(
            context, **response_kwargs)
        if response.streaming or response.status_code != 200:
            return response

        def update_cache(key, value, timeout):
            """ add_post_render_callback modify the response
                if this function return other than None
            """
            cache = get_cache("default")
            cache.set(key, value, timeout)
            return None

        timeout = self.get_cache_timeout()
        cache_key = self.request.META["PATH_INFO"]
        if hasattr(response, 'render') and callable(response.render):
            response.add_post_render_callback(
                lambda r: update_cache(
                    key=cache_key, value=response, timeout=timeout)
            )
        else:
            update_cache(key=cache_key, value=response, timeout=timeout)
        return response
