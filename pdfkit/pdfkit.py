# -*- coding: utf-8 -*-
import re
import subprocess
import sys
from .source import Source
from .configuration import Configuration
from itertools import chain
import io
import codecs
import time


class PDFKit(object):
    """
    Main class that does all generation routine.

    :param url_or_file: str - either a URL, a path to a file or a string containing HTML
                       to convert
    :param type_: str - either 'url', 'file' or 'string'
    :param options: dict (optional) with wkhtmltopdf options, with or w/o '--'
    :param toc: dict (optional) - toc-specific wkhtmltopdf options, with or w/o '--'
    :param cover: str (optional) - url/filename with a cover html page
    :param configuration: (optional) instance of pdfkit.configuration.Configuration()
    """

    class ImproperSourceError(Exception):
        """Wrong source type for stylesheets"""

        def __init__(self, msg):
            self.msg = msg

        def __str__(self):
            return self.msg

    def __init__(self, url_or_file, type_, options=None, toc=None, cover=None,
                 css=None, configuration=None):

        print "starting init of object"
        self.source = Source(url_or_file, type_)
        self.configuration = (Configuration() if configuration is None
                              else configuration)
        self.wkhtmltopdf = self.configuration.wkhtmltopdf.decode('utf-8')

        self.options = dict()
        if self.source.isString():
            self.options.update(self._find_options_in_meta(url_or_file))
        if options is not None: self.options.update(options)
        self.options = self._normalize_options(self.options)

        toc = {} if toc is None else toc
        self.toc = self._normalize_options(toc)
        self.cover = cover
        self.css = css
        self.stylesheets = []
        print "ending init of object"

    def command(self, path=None):
        if self.css:
            self._prepend_css(self.css)

        args = [self.wkhtmltopdf]

        args += list(chain.from_iterable(list(self.options.items())))
        args = [_f for _f in args if _f]

        if self.toc:
            args.append('toc')
            args += list(chain.from_iterable(list(self.toc.items())))
        if self.cover:
            args.append('cover')
            args.append(self.cover)

        # If the source is a string then we will pipe it into wkhtmltopdf
        # If the source is file-like then we will read from it and pipe it in
        if self.source.isString() or self.source.isFileObj():
            args.append('-')
        else:
            if isinstance(self.source.source, str):
                args.append(self.source.to_s())
            else:
                args += self.source.source

        # If output_path evaluates to False append '-' to end of args
        # and wkhtmltopdf will pass generated PDF to stdout
        if path:
            args.append(path)
        else:
            args.append('-')

        return args

    def to_pdf(self, path=None):
        print "starting to_pdf"
        print "path is ", path
        args = self.command(path)

        print "args is ", args
        print "setting bufsize and uni newline and stdin is None"
        result = subprocess.Popen(args, stdin=None, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, bufsize=600000, universal_newlines=True)

        # If the source is a string then we will pipe it into wkhtmltopdf.
        # If we want to add custom CSS to file then we read input file to
        # string and prepend css to it and then pass it to stdin.
        # This is a workaround for a bug in wkhtmltopdf (look closely in README)
        """if self.source.isString() or (self.source.isFile() and self.css):
            print "here 1"
            input = self.source.to_s().encode('utf-8')
        elif self.source.isFileObj():
            print "here 2"
            input = self.source.source.read().encode('utf-8')
        else:
            print "input is none"
            input = None
        print "input is ", input"""
        stdout, stderr = result.communicate(input=None)

        """done = False
        attempts = 0
        MAX_ATTEMPTS = 5
        while not done and attempts < MAX_ATTEMPTS:
            ret = result.poll()
            attempts += 1
            if ret == 0:
                done = True
                print "I'm done"
                continue
            else:
                print "sleeping 4 trying again"
                time.sleep(4)"""

        print "stderr is ", stderr

        if not stderr:
            stderr = ''

        exit_code = result.returncode
        print "the exit coe was ", exit_code

        if 'cannot connect to X server' in stderr.decode('utf-8'):
            raise IOError('%s\n'
                          'You will need to run whktmltopdf within a "virutal" X server.\n'
                          'Go to the link above for more information\n'
                          'https://github.com/JazzCore/python-pdfkit/wiki/Using-wkhtmltopdf-without-X-server' % stderr.decode('utf-8'))

        if 'Error' in stderr.decode('utf-8'):
            raise IOError('wkhtmltopdf reported an error:\n' + stderr.decode('utf-8'))

        if exit_code != 0:
            raise IOError("wkhtmltopdf exited with non-zero code {0}. error:\n{1}".format(exit_code, stderr.decode("utf-8")))

        # Since wkhtmltopdf sends its output to stderr we will capture it
        # and properly send to stdout
        if '--quiet' not in args:
            sys.stdout.write(stderr.decode('utf-8'))

        if not path:
            print "here 42"
            return stdout
        else:
            try:
                with codecs.open(path, encoding='utf-8') as f:
                    # read 4 bytes to get PDF signature '%PDF'
                    print "here 43"
                    text = f.read(4)
                    if text == '':
                        raise IOError('Command failed: %s\n'
                                      'Check whhtmltopdf output without \'quiet\' '
                                      'option' % ' '.join(args))
                    return True
            except IOError:
                raise IOError('Command failed: %s\n'
                              'Check whhtmltopdf output without \'quiet\' option' %
                              ' '.join(args))

    def _normalize_options(self, options):
        """Updates a dict of config options to make then usable on command line

        :param options: dict {option name: value}

        returns:
          dict: {option name: value} - option names lower cased and prepended with
                                       '--' if necessary. Non-empty values cast to str
        """
        normalized_options = {}

        for key, value in list(options.items()):
            if not '--' in key:
                normalized_key = '--%s' % self._normalize_arg(key)
            else:
                normalized_key = self._normalize_arg(key)
            normalized_options[normalized_key] = str(value) if value else value

        return normalized_options

    def _normalize_arg(self, arg):
        return arg.lower()

    def _style_tag_for(self, stylesheet):
        return "<style>%s</style>" % stylesheet

    def _prepend_css(self, path):
        if self.source.isUrl() or isinstance(self.source.source, list):
            raise self.ImproperSourceError('CSS files can be added only to a single '
                                           'file or string')

        if not isinstance(path, list):
            path = [path]

        css_data = []
        for p in path:
            with codecs.open(p, encoding="UTF-8") as f:
                css_data.append(f.read())
        css_data = "\n".join(css_data)

        if self.source.isFile():
            with codecs.open(self.source.to_s(), encoding="UTF-8") as f:
                inp = f.read()
            self.source = Source(
                inp.replace('</head>', self._style_tag_for(css_data) + '</head>'),
                'string')

        elif self.source.isString():
            if '</head>' in self.source.to_s():
                self.source.source = self.source.to_s().replace(
                    '</head>', self._style_tag_for(css_data) + '</head>')
            else:
                self.source.source = self._style_tag_for(css_data) + self.source.to_s()

    def _find_options_in_meta(self, content):
        """Reads 'content' and extracts options encoded in HTML meta tags

        :param content: str or file-like object - contains HTML to parse

        returns:
          dict: {config option: value}
        """
        if (isinstance(content, io.IOBase)
                or content.__class__.__name__ == 'StreamReaderWriter'):
            content = content.read()

        found = {}

        for x in re.findall('<meta [^>]*>', content):
            if re.search('name=["\']%s' % self.configuration.meta_tag_prefix, x):
                name = re.findall('name=["\']%s([^"\']*)' %
                                  self.configuration.meta_tag_prefix, x)[0]
                found[name] = re.findall('content=["\']([^"\']*)', x)[0]

        return found
