# -*- coding: utf-8 -*-
'''
Use the ``mockups`` command like this::

    django-admin.py mockups [options] app.Model:# [app.Model:# ...]

Its nearly self explanatory. Supply names of models, prefixed with their app
name. After that, place a colon and tell the command how many objects you want
to create. Here is an example of how to create three categories and twenty
entries for you blogging app::

    django-admin.py mockups blog.Category:3 blog.Entry:20

Voila! You have ready to use testing data populated to your database. The
model fields are filled with data by producing randomly generated values
depending on the type of the field. E.g. text fields are filled with lorem
ipsum dummies, date fields are populated with random dates from the last
years etc.

There are a few command line options available. Mainly to control the
behavior of related fields. If foreingkey or many to many fields should be
populated with existing data or if the related models are also generated on
the fly. Please have a look at the help page of the command for more
information::

    django-admin.py help mockups
'''
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.db import transaction
from django.apps import apps
from importlib import import_module
from ...helpers import create, autodiscover
from ... import signals
from optparse import make_option


class Command(BaseCommand):
    help = (
        u'Create random model instances for testing purposes.'
    )
    args = 'app.Model:# [app.Model:# ...]'

    def add_arguments(self, args):
        # Positional arguments
        args.add_argument('app', nargs='+', type=str)

        # Named (optional) arguments
        args.add_argument(
            '--no-follow-fk',
            action='store_true',
            dest='no_follow_fk',
            default=False,
            help='Delete poll instead of closing it',
        )

        args.add_argument(
            '--generate-fk',
            action='store',
            dest='generate_fk',
            default=None,
            help=u'Do not use already existing instances for ForeignKey '
            u'relations. Create new instances instead. You can specify a '
            u'comma sperated list of field names or ALL to indicate that '
            u'all foreignkeys should be generated automatically.',
        )

        args.add_argument(
            '--no-follow-m2m',
            action='store_true',
            dest='no_follow_m2m',
            default=None,
            help=u'Ignore many to many fields while creating model '
            u'instances.',
        )

        args.add_argument(
            '--follow-m2m',
            action='store',
            dest='follow_m2m',
            default=None,
            help=u'Specify minimum and maximum number of instances that are '
            u'assigned to a m2m relation. Use two, colon separated '
            u'numbers in the form of: min,max. Default is 1,5.\n'
            u'You can limit following of many to many relations to '
            u'specific fields using the following format:\n'
            u'field1:min:max,field2:min:max ...',
        )

        args.add_argument(
            '--generate-m2m',
            action='store',
            dest='generate_m2m',
            default=None,
            help=u'Specify minimum and maximum number of instances that are '
            u'newly created and assigned to a m2m relation. Use two, '
            u'colon separated numbers in the form of: min:max. Default is '
            u'to not generate many to many related models automatically. '
            u'You can select specific of many to many fields which are '
            u'automatically generated. Use the following format:\n'
            u'field1:min:max,field2:min:max ...',
        )

        args.add_argument(
            '-u', '--use',
            action='store',
            dest='use',
            default=None,
            help=u'Specify a mockup subclass that is used to create the '
            u'test data. E.g. myapp.mockup.MyMockup',
        )

    def format_output(self, obj):
        output = unicode(obj)
        if len(output) > 50:
            output = u'%s ...' % output[:50]
        return output

    def print_instance(self, sender, model, instance, **kwargs):
        if self.verbosity < 1:
            return
        print '%s(pk=%s): %s' % (
            '%s.%s' % (
                model._meta.app_label,
                model._meta.object_name),
            unicode(instance.pk),
            self.format_output(instance),
        )
        if self.verbosity < 2:
            return
        for field in instance._meta.fields:
            if isinstance(field, models.ForeignKey):
                obj = getattr(instance, field.name)
                if isinstance(obj, models.Model):
                    print '|   %s (pk=%s): %s' % (
                        field.name,
                        obj.pk,
                        self.format_output(obj))
        for field in instance._meta.many_to_many:
            qs = getattr(instance, field.name).all()
            if qs.count():
                print '|   %s (count=%d):' % (
                    field.name,
                    qs.count())
                for obj in qs:
                    print '|   |   (pk=%s): %s' % (
                        obj.pk,
                        self.format_output(obj))


    # open a transaction
    def handle(self, *attrs, **options):
        error_option = None
        #
        # follow options
        #
        print (attrs)
        print (options)
        if options['no_follow_fk'] is None:
            follow_fk = None
        else:
            follow_fk = False
        if options['no_follow_m2m'] is None:
            follow_m2m = None
            # this is the only chance for the follow_m2m options to be parsed
            if options['follow_m2m']:
                try:
                    value = options['follow_m2m'].split(',')
                    if len(value) == 1 and value[0].count(':') == 1:
                        follow_m2m = [int(i) for i in value[0].split(':')]
                    else:
                        follow_m2m = {}
                        for field in value:
                            key, minval, maxval = field.split(':')
                            follow_m2m[key] = int(minval), int(maxval)
                except ValueError:
                    error_option = '--follow-m2m=%s' % options['follow_m2m']
        else:
            follow_m2m = False
        #
        # generation options
        #
        if options['generate_fk'] is None:
            generate_fk = None
        else:
            generate_fk = options['generate_fk'].split(',')
        generate_m2m = None
        if options['generate_m2m']:
            try:
                value = [v for v in options['generate_m2m'].split(',') if v]
                if len(value) == 1 and value[0].count(':') == 1:
                    generate_m2m = [int(i) for i in value[0].split(':')]
                else:
                    generate_m2m = {}
                    for field in value:
                        key, minval, maxval = field.split(':')
                        generate_m2m[key] = int(minval), int(maxval)
            except ValueError:
                error_option = '--generate-m2m=%s' % options['generate_m2m']

        if error_option:
            raise CommandError(
                u'Invalid option %s\n'
                u'Expected: %s=field:min:max,field2:min:max... (min and max must be numbers)' % (
                    error_option,
                    error_option.split('=', 1)[0]))

        use = options['use']
        if use:
            use = use.split('.')
            use = getattr(import_module('.'.join(use[:-1])), use[-1])

        self.verbosity = int(options['verbosity'])

        models = []
        for attr in options['app']:
            try:
                app_label, model_label = attr.split('.')
                model_label, count = model_label.split(':')
                count = int(count)
            except ValueError:
                raise CommandError(
                    u'Invalid argument: %s\n'
                    u'Expected: app_label.ModelName:count '
                    u'(count must be a number)' % (
                        attr,
                    )
                )
            model = apps.get_model(app_label, model_label)
            if not model:
                raise CommandError(
                    u'Unknown model: %s.%s' % (app_label, model_label))
            models.append((model, count))

        signals.instance_created.connect(
            self.print_instance)

        autodiscover()

        kwargs = {
            'follow_fk': bool(follow_fk),
            'generate_fk': bool(generate_fk),
            'follow_m2m': bool(follow_m2m),
            'generate_m2m': bool(generate_m2m),
        }

        print (kwargs)
        for model, count in models:
            if use:
                mockup = use(model, **kwargs)
                mockup.create(count)
            else:
                create(model, count, **kwargs)
