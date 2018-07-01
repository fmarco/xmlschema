#
# Copyright (c), 2016-2018, SISSA (International School for Advanced Studies).
# All rights reserved.
# This file is distributed under the terms of the MIT License.
# See the file 'LICENSE' in the root directory of the present
# distribution, or http://opensource.org/licenses/MIT.
#
# @author Davide Brunato <brunato@sissa.it>
#
"""
This module contains converter classes and definitions.
"""
from collections import namedtuple, OrderedDict
import string

from .exceptions import XMLSchemaValueError
from .etree import etree_element, etree_register_namespace, lxml_element, lxml_register_namespace
from .namespaces import NamespaceMapper


ElementData = namedtuple('ElementData', ['tag', 'text', 'content', 'attributes'])
"Namedtuple for Element data interchange between decoders and converters."


class XMLSchemaConverter(NamespaceMapper):
    """
    Generic XML Schema based converter class. A converter is used to compose
    decoded XML data for an Element into a data structure and to build an Element
    from encoded data structure.

    :param namespaces: Map from namespace prefixes to URI.
    :param dict_class: Dictionary class to use for decoded data. Default is `dict`.
    :param list_class: List class to use for decoded data. Default is `list`.
    :param text_key: is the key to apply to element's decoded text data.
    :param attr_prefix: controls the mapping of XML attributes, to the same name or \
    with a prefix. If `None` the converter ignores attributes.
    :param cdata_prefix: is used for including and prefixing the CDATA parts of a \
    mixed content, that are labeled with an integer instead of a string. \
    CDATA parts are ignored if this argument is `None`.
    :param etree_element_class: the class that has to be used to create new XML elements.
    :param indent: Number of spaces for XML indentation (default is 4).
    """
    def __init__(self, namespaces=None, dict_class=None, list_class=None, text_key='$', attr_prefix='@',
                 cdata_prefix=None, etree_element_class=etree_element, indent=4, **kwargs):
        if etree_element_class not in (etree_element, lxml_element):
            raise XMLSchemaValueError("%r: unsupported element.")
        self.dict = dict_class or dict
        self.list = list_class or list
        self.text_key = text_key
        self.attr_prefix = attr_prefix
        self.cdata_prefix = cdata_prefix
        self.etree_element_class = etree_element_class
        self.indent = indent
        super(XMLSchemaConverter, self).__init__(namespaces)

    def __setattr__(self, name, value):
        if name in ('attr_prefix', 'text_key', 'cdata_prefix'):
            if value is not None and any(c in string.ascii_letters or c == '_' for c in value):
                raise XMLSchemaValueError('%r cannot includes letters or underscores: %r' % (name, value))
            elif name == 'attr_prefix':
                self.ns_prefix = (value or '') + 'xmlns'
        super(NamespaceMapper, self).__setattr__(name, value)

    def copy(self, **kwargs):
        return type(self)(
            namespaces=kwargs.get('namespaces', self._namespaces),
            dict_class=kwargs.get('dict_class', self.dict),
            list_class=kwargs.get('list_class', self.list),
            text_key=kwargs.get('text_key', self.text_key),
            attr_prefix=kwargs.get('attr_prefix', self.attr_prefix),
            cdata_prefix=kwargs.get('cdata_prefix', self.cdata_prefix),
            etree_element_class=kwargs.get('etree_element_class', self.etree_element_class),
            indent=kwargs.get('indent', self.indent),
        )

    def map_attributes(self, attributes):
        """
        Creates an iterator for converting decoded attributes to a data structure with
        appropriate prefixes. If the instance has a not-empty map of namespaces registers
        the mapped URIs and prefixes.

        :param attributes: A sequence or an iterator of couples with the name of \
        the attribute and the decoded value. Default is `None` (for `simpleType` \
        elements, that don't have attributes).
        """
        if self.attr_prefix is None or not attributes:
            return
        elif self.attr_prefix:
            for name, value in attributes:
                yield u'%s%s' % (self.attr_prefix, self.map_qname(name)), value
        else:
            for name, value in attributes:
                yield self.map_qname(name), value

    def unmap_attribute_qname(self, name):
        if name[0] == '{' or ':' not in name:
            return name
        else:
            return self.unmap_qname(name)

    def map_content(self, content):
        """
        A generator function for converting decoded content to a data structure.
        If the instance has a not-empty map of namespaces registers the mapped URIs
        and prefixes.

        :param content: A sequence or an iterator of tuples with the name of the \
        element, the decoded value and the `XsdElement` instance associated.
        """
        map_qname = self.map_qname
        for name, value, xsd_child in content:
            try:
                if name[0] == '{':
                    yield map_qname(name), value, xsd_child
                else:
                    yield name, value, xsd_child
            except TypeError:
                if self.cdata_prefix is not None:
                    yield u'%s%s' % (self.cdata_prefix, name), value, xsd_child

    def etree_element(self, tag, text=None, children=None, attrib=None, level=0):
        """
        Builds an ElementTree's Element using arguments and the element class and
        the indent spacing stored in the converter instance.
        """
        if type(self.etree_element_class) is type(etree_element):
            if attrib is None:
                elem = self.etree_element_class(tag)
            else:
                elem = self.etree_element_class(tag, self.dict(attrib))
        else:
            nsmap = {prefix if prefix else None: uri for prefix, uri in self._namespaces.items()}
            elem = self.etree_element_class(tag, self.dict(attrib), nsmap)

        if children:
            elem.extend(children)
            elem.text = text or u'\n' + u' ' * self.indent * (level + 1)
            elem.tail = u'\n' + u' ' * self.indent * level
        else:
            elem.text = text
            elem.tail = u'\n' + u' ' * self.indent * level

        return elem

    def element_decode(self, data, xsd_element, include_namespaces=False):
        """
        Converts a decoded element data to a data structure.

        :param data: Decoded ElementData from an Element node.
        :param xsd_element: The `XsdElement` associated to decoded the data.
        :param include_namespaces: If set to `True` namespace information are included in the decode data.
        :return: A dictionary-based data structure containing the decoded data.
        """
        result_dict = self.dict()
        if include_namespaces:
            result_dict.update(
                (u'%s:%s' % (self.ns_prefix, k) if k else self.ns_prefix, v) for k, v in self.items()
            )

        if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
            if data.attributes:
                result_dict.update(t for t in self.map_attributes(data.attributes))
                if data.text is not None and data.text != '':
                    result_dict[self.text_key] = data.text
                return result_dict
            else:
                return data.text if data.text != '' else None
        else:
            if data.attributes:
                result_dict.update(t for t in self.map_attributes(data.attributes))

            for name, value, xsd_child in self.map_content(data.content):
                try:
                    result_dict[name].append(value)
                except KeyError:
                    if xsd_child is None or xsd_child.is_single() and \
                            xsd_element.type.content_type.is_single() and not isinstance(value, (self.list, list)):
                        result_dict[name] = value
                    else:
                        result_dict[name] = self.list([value])
                except AttributeError:
                    result_dict[name] = self.list([result_dict[name], value])
            return result_dict if result_dict else None

    def element_encode(self, obj, xsd_element):
        """
        Extracts XML decoded data from a data structure for encoding into an ElementTree.

        :param obj: the decoded object.
        :param xsd_element: The `XsdElement` associated to the decoded data structure.
        :return: An ElementData instance.
        """
        if not isinstance(obj, (self.dict, dict)):
            if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
                return ElementData(xsd_element.name, obj, None, self.dict())
            else:
                return ElementData(xsd_element.name, None, obj, self.dict())

        unmap_qname = self.unmap_qname
        unmap_attribute_qname = self.unmap_attribute_qname
        text_key = self.text_key
        attr_prefix = self.attr_prefix
        ns_prefix = self.ns_prefix
        cdata_prefix = self.cdata_prefix

        text = None
        content = []
        attributes = self.dict()
        for name, value in obj.items():
            if text_key and name == text_key:
                text = obj[text_key]
            elif (cdata_prefix and name.startswith(cdata_prefix)) or \
                    name[0].isdigit() and cdata_prefix == '':
                index = int(name[len(cdata_prefix):])
                content.append((index, value))
            elif name == ns_prefix:
                self[''] = value
            elif name.startswith('%s:' % ns_prefix):
                self[name[len(ns_prefix)+1:]] = value
            elif attr_prefix and name.startswith(attr_prefix):
                name = name[len(attr_prefix):]
                attributes[unmap_attribute_qname(name)] = value
            elif not isinstance(value, (self.list, list)) or not value:
                content.append((unmap_qname(name), value))
            elif isinstance(value[0], (self.dict, dict, self.list, list)):
                ns_name = unmap_qname(name)
                for item in value:
                    content.append((ns_name, item))
            else:
                ns_name = unmap_qname(name)
                for xsd_child in xsd_element.type.content_type.iter_elements():
                    if xsd_child.match(ns_name):
                        if xsd_child.type.is_list():
                            content.append((ns_name, value))
                        else:
                            for item in value:
                                content.append((ns_name, item))
                        break
                else:
                    if attr_prefix == '' and ns_name not in attributes:
                        for xsd_attribute in xsd_element.attributes.values():
                            if xsd_attribute.match(ns_name):
                                attributes[ns_name] = value
                                break
                        else:
                            content.append((ns_name, value))
                    else:
                        content.append((ns_name, value))

        return ElementData(xsd_element.name, text, content, attributes)


class ParkerConverter(XMLSchemaConverter):
    """
    XML Schema based converter class for Parker convention.

    ref: http://wiki.open311.org/JSON_and_XML_Conversion/#the-parker-convention

    :param namespaces: Map from namespace prefixes to URI.
    :param dict_class: Dictionary class to use for decoded data. Default is `OrderedDict`.
    :param list_class: List class to use for decoded data. Default is `list`.
    :param preserve_root: If `True` the root element will be preserved. For default \
    the Parker convention remove the document root element, returning only the value.
    """
    def __init__(self, namespaces=None, dict_class=None, list_class=None, preserve_root=False, **kwargs):
        kwargs.update(attr_prefix=None, text_key='', cdata_prefix=None)
        super(ParkerConverter, self).__init__(
            namespaces, dict_class or OrderedDict, list_class, **kwargs
        )
        self.preserve_root = preserve_root

    def copy(self, **kwargs):
        return type(self)(
            namespaces=kwargs.get('namespaces', self._namespaces),
            dict_class=kwargs.get('dict_class', self.dict),
            list_class=kwargs.get('list_class', self.list),
            preserve_root=kwargs.get('preserve_root', self.preserve_root),
            etree_element_class=kwargs.get('etree_element_class', self.etree_element_class),
            indent=kwargs.get('indent', self.indent),
        )

    def element_decode(self, data, xsd_element, *args, **kwargs):
        map_qname = self.map_qname
        preserve_root = self.preserve_root
        if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
            if preserve_root:
                return self.dict([(map_qname(data.tag), data.text)])
            else:
                return data.text if data.text != '' else None
        else:
            result_dict = self.dict()
            for name, value, xsd_child in self.map_content(data.content):
                if preserve_root:
                    try:
                        if len(value) == 1:
                            value = value[name]
                    except (TypeError, KeyError):
                        pass

                try:
                    result_dict[name].append(value)
                except KeyError:
                    if isinstance(value, (self.list, list)):
                        result_dict[name] = self.list([value])
                    else:
                        result_dict[name] = value
                except AttributeError:
                    result_dict[name] = self.list([result_dict[name], value])

            for k, v in result_dict.items():
                if isinstance(v, (self.list, list)) and len(v) == 1:
                    value = v.pop()
                    v.extend(value)

            if preserve_root:
                return self.dict([(map_qname(data.tag), result_dict)])
            else:
                return result_dict if result_dict else None

    def element_encode(self, obj, xsd_element):
        if not isinstance(obj, (self.dict, dict)):
            if obj == '':
                obj = None
            if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
                return ElementData(xsd_element.name, obj, None, self.dict())
            else:
                return ElementData(xsd_element.name, None, obj, self.dict())
        else:
            unmap_qname = self.unmap_qname
            if not obj:
                return ElementData(xsd_element.name, None, None, self.dict())
            elif self.preserve_root:
                try:
                    items = obj[self.map_qname(xsd_element.name)]
                except KeyError:
                    return ElementData(xsd_element.name, None, None, self.dict())
            else:
                items = obj

            try:
                content = []
                for name, value in obj.items():
                    ns_name = unmap_qname(name)
                    if not isinstance(value, (self.list, list)) or not value:
                        content.append((ns_name, value))
                    elif any(isinstance(v, (self.list, list)) for v in value):
                        for item in value:
                            content.append((ns_name, item))
                    else:
                        for xsd_child in xsd_element.type.content_type.iter_elements():
                            if xsd_child.match(ns_name):
                                if xsd_child.type.is_list():
                                    content.append((ns_name, value))
                                else:
                                    for item in value:
                                        content.append((ns_name, item))
                                break
                        else:
                            for item in value:
                                content.append((ns_name, item))

            except AttributeError:
                return ElementData(xsd_element.name, items, None, self.dict())
            else:
                return ElementData(xsd_element.name, None, content, self.dict())


class BadgerFishConverter(XMLSchemaConverter):
    """
    XML Schema based converter class for Badgerfish convention.

    ref: http://www.sklar.com/badgerfish/
    ref: http://badgerfish.ning.com/

    :param namespaces: Map from namespace prefixes to URI.
    :param dict_class: Dictionary class to use for decoded data. Default is `OrderedDict`.
    :param list_class: List class to use for decoded data. Default is `list`.
    """
    def __init__(self, namespaces=None, dict_class=None, list_class=None, **kwargs):
        kwargs.update(attr_prefix='@', text_key='$', cdata_prefix='#')
        super(BadgerFishConverter, self).__init__(
            namespaces, dict_class or OrderedDict, list_class, **kwargs
        )

    def element_decode(self, data, xsd_element, include_namespaces=True):
        dict_class = self.dict

        tag = self.map_qname(data.tag)
        has_local_root = not len(self)
        result_dict = dict_class([t for t in self.map_attributes(data.attributes)])
        if has_local_root:
            result_dict[u'@xmlns'] = dict_class()

        if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
            if data.text is not None and data.text != '':
                result_dict[self.text_key] = data.text
        else:
            for name, value, xsd_child in self.map_content(data.content):
                try:
                    if u'@xmlns' in value:
                        self.transfer(value[u'@xmlns'])
                        if not value[u'@xmlns']:
                            del value[u'@xmlns']
                    elif u'@xmlns' in value[name]:
                        self.transfer(value[name][u'@xmlns'])
                        if not value[name][u'@xmlns']:
                            del value[name][u'@xmlns']
                    if len(value) == 1:
                        value = value[name]
                except (TypeError, KeyError):
                    pass

                if value is None:
                    value = self.dict()

                try:
                    result_dict[name].append(value)
                except KeyError:
                    if xsd_child is None or xsd_child.is_single():
                        result_dict[name] = value
                    else:
                        result_dict[name] = self.list([value])
                except AttributeError:
                    result_dict[name] = self.list([result_dict[name], value])

        if has_local_root:
            if self:
                result_dict[u'@xmlns'].update(self)
            else:
                del result_dict[u'@xmlns']
            return dict_class([(tag, result_dict)])
        else:
            return dict_class([('@xmlns', dict_class(self)), (tag, result_dict)])

    def element_encode(self, obj, xsd_element):
        map_qname = self.map_qname
        unmap_qname = self.unmap_qname
        unmap_attribute_qname = self.unmap_attribute_qname

        try:
            self.update(obj[u'@xmlns'])
        except KeyError:
            pass

        try:
            element_data = obj[map_qname(xsd_element.name)]
        except KeyError:
            element_data = obj

        text_key = self.text_key
        attr_prefix = self.attr_prefix
        cdata_prefix = self.cdata_prefix
        text = None
        content = []
        attributes = self.dict()
        for name, value in element_data.items():
            if name == u'@xmlns':
                continue
            elif text_key and name == text_key:
                text = element_data[text_key]
            elif (cdata_prefix and name.startswith(cdata_prefix)) or \
                    name[0].isdigit() and cdata_prefix == '':
                index = int(name[len(cdata_prefix):])
                content.append((index, value))
            elif attr_prefix and name.startswith(attr_prefix):
                name = name[len(attr_prefix):]
                attributes[unmap_attribute_qname(name)] = value
            elif not isinstance(value, (self.list, list)) or not value:
                content.append((unmap_qname(name), value))
            elif isinstance(value[0], (self.dict, dict, self.list, list)):
                ns_name = unmap_qname(name)
                for item in value:
                    content.append((ns_name, item))
            else:
                ns_name = unmap_qname(name)
                for xsd_child in xsd_element.type.content_type.iter_elements():
                    if xsd_child.match(ns_name):
                        if xsd_child.type.is_list():
                            content.append((ns_name, value))
                        else:
                            for item in value:
                                content.append((ns_name, item))
                        break
                else:
                    if attr_prefix == '' and ns_name not in attributes:
                        for xsd_attribute in xsd_element.attributes.values():
                            if xsd_attribute.match(ns_name):
                                attributes[ns_name] = value
                                break
                        else:
                            content.append((ns_name, value))
                    else:
                        content.append((ns_name, value))

        return ElementData(xsd_element.name, text, content, attributes)


class AbderaConverter(XMLSchemaConverter):
    """
    XML Schema based converter class for Abdera convention.

    ref: http://wiki.open311.org/JSON_and_XML_Conversion/#the-abdera-convention
    ref: https://cwiki.apache.org/confluence/display/ABDERA/JSON+Serialization

    :param namespaces: Map from namespace prefixes to URI.
    :param dict_class: Dictionary class to use for decoded data. Default is `OrderedDict`.
    :param list_class: List class to use for decoded data. Default is `list`.
    """
    def __init__(self, namespaces=None, dict_class=None, list_class=None, **kwargs):
        kwargs.update(attr_prefix='', text_key='', cdata_prefix=None)
        super(AbderaConverter, self).__init__(
            namespaces, dict_class or OrderedDict, list_class, **kwargs
        )

    def element_decode(self, data, xsd_element, *args, **kwargs):
        if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
            children = data.text if data.text is not None and data.text != '' else None
        else:
            children = self.dict()
            for name, value, xsd_child in self.map_content(data.content):
                if value is None:
                    value = self.list()

                try:
                    children[name].append(value)
                except KeyError:
                    if isinstance(value, (self.list, list)) and value:
                        children[name] = self.list([value])
                    else:
                        children[name] = value
                except AttributeError:
                    children[name] = self.list([children[name], value])
            if not children:
                children = None

        if data.attributes:
            if children:
                return self.dict([
                    ('attributes', self.dict([(k, v) for k, v in self.map_attributes(data.attributes)])),
                    ('children', self.list([children]) if children is not None else self.list())
                ])
            else:
                return self.dict([
                    ('attributes', self.dict([(k, v) for k, v in self.map_attributes(data.attributes)])),
                ])
        else:
            return children if children is not None else self.list()

    def element_encode(self, obj, xsd_element):
        if not isinstance(obj, (self.dict, dict)):
            if obj == []:
                obj = None
            return ElementData(xsd_element.name, obj, None, self.dict())
        else:
            unmap_qname = self.unmap_qname
            unmap_attribute_qname = self.unmap_attribute_qname
            attributes = self.dict()
            try:
                attributes.update([(unmap_attribute_qname(k), v) for k, v in obj['attributes'].items()])
            except KeyError:
                children = obj
            else:
                children = obj.get('children', [])

            if isinstance(children, (self.dict, dict)):
                children = [children]
            elif children and not isinstance(children[0], (self.dict, dict)):
                if len(children) > 1:
                    raise ValueError("Wrong format")
                else:
                    return ElementData(xsd_element.name, children[0], None, attributes)

            content = []
            for child in children:
                for name, value in child.items():
                    if not isinstance(value, (self.list, list)) or not value:
                        content.append((unmap_qname(name), value))
                    elif isinstance(value[0], (self.dict, dict, self.list, list)):
                        ns_name = unmap_qname(name)
                        for item in value:
                            content.append((ns_name, item))
                    else:
                        ns_name = unmap_qname(name)
                        for xsd_child in xsd_element.type.content_type.iter_elements():
                            if xsd_child.match(ns_name):
                                if xsd_child.type.is_list():
                                    content.append((ns_name, value))
                                else:
                                    for item in value:
                                        content.append((ns_name, item))
                                break
                        else:
                            content.append((ns_name, value))

            return ElementData(xsd_element.name, None, content, attributes)


class JsonMLConverter(XMLSchemaConverter):
    """
    XML Schema based converter class for JsonML (JSON Mark-up Language) convention.

    ref: http://www.jsonml.org/
    ref: https://www.ibm.com/developerworks/library/x-jsonml/

    :param namespaces: Map from namespace prefixes to URI.
    :param dict_class: Dictionary class to use for decoded data. Default is `OrderedDict`.
    :param list_class: List class to use for decoded data. Default is `list`.
    """
    def __init__(self, namespaces=None, dict_class=None, list_class=None, **kwargs):
        kwargs.update(attr_prefix='', text_key='', cdata_prefix=None)
        super(JsonMLConverter, self).__init__(
            namespaces, dict_class or OrderedDict, list_class, **kwargs
        )

    def element_decode(self, data, xsd_element, include_namespaces=True):
        result_list = self.list([self.map_qname(data.tag)])
        attributes = self.dict([(k, v) for k, v in self.map_attributes(data.attributes)])

        if xsd_element.type.is_simple() or xsd_element.type.has_simple_content():
            if data.text is not None and data.text != '':
                result_list.append(data.text)
        else:
            result_list.extend([
                value if value is not None else self.list([name])
                for name, value, _ in self.map_content(data.content)
            ])

        if self and include_namespaces:
            attributes.update([('xmlns:%s' % k if k else 'xmlns', v) for k, v in self.items()])
        if attributes:
            result_list.insert(1, attributes)
        return result_list

    def element_encode(self, obj, xsd_element):
        unmap_qname = self.unmap_qname
        attributes = self.dict()
        if not isinstance(obj, (self.list, list)) or not obj:
            raise ValueError("Wrong data format, a not empty list required: %r." % obj)

        data_len = len(obj)
        if data_len == 1:
            if not xsd_element.match(unmap_qname(obj[0]), default_namespace=self.get('')):
                raise ValueError("Unmatched tag")
            return ElementData(xsd_element.name, None, None, attributes)

        unmap_attribute_qname = self.unmap_attribute_qname
        try:
            for k, v in obj[1].items():
                if k == 'xmlns':
                    self[''] = v
                elif k.startswith('xmlns:'):
                    self[k.split('xmlns:')[1]] = v
                else:
                    attributes[unmap_attribute_qname(k)] = v
        except AttributeError:
            content_index = 1
        else:
            content_index = 2

        if not xsd_element.match(unmap_qname(obj[0]), self.get('')):
            raise ValueError("Unmatched tag")

        if data_len <= content_index:
            return ElementData(xsd_element.name, None, [], attributes)
        elif data_len > content_index + 1 or isinstance(obj[content_index], (self.list, list)) \
                and not xsd_element.type.is_list():
            content = [(unmap_qname(e[0]), e) for e in obj[content_index:]]
            return ElementData(xsd_element.name, None, content, attributes)
        else:
            return ElementData(xsd_element.name, obj[content_index], [], attributes)
