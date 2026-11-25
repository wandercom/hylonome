"""Escaped rich slot values for content compositions; no language decisions."""
from html import escape


def inline(value):
    from .html import element
    if isinstance(value, str):return escape(value)
    chunks = []
    for run in value:
        if isinstance(run,str):chunks.append(escape(run));continue
        text = escape(run['text'])
        if run.get('em'):text = element('em',{},text)
        if run.get('strong'):text = element('strong',{},text)
        if 'href' in run:text = element('a',{'href':run['href']},text)
        chunks.append(text)
    return ''.join(chunks)


def media(value, attrs=None):
    from .html import element
    image = element('img', {'src':value['src'],'alt':value['alt'],'loading':'eager'})
    notes = [escape(value[key]) for key in ('caption','credit') if value.get(key)]
    if notes:image += element('figcaption',{},' · '.join(notes))
    return element('figure',attrs or {},image)


def links(values, listed=False, items=False):
    from .html import element
    chunks = [element('a',{'href':item['href'],'data-kd-part':'link' if listed else None,
                           'aria-current':'page' if item.get('current') else None},escape(item['text'])) for item in values]
    if items:return ''.join(element('li',{},chunk) for chunk in chunks)  # The slot element is itself the list.
    if listed:return element('ul',{},''.join(element('li',{},chunk) for chunk in chunks))
    return ''.join(chunks)


def control(spec):
    """Native form controls from a data description; every value is escaped."""
    from .html import element
    kind = spec.get('type','text')
    common = {'id':spec.get('id'),'name':spec.get('name'),'disabled':'' if spec.get('disabled') else None,
              'required':'' if spec.get('required') else None,'aria-invalid':'true' if spec.get('invalid') else None,
              'aria-describedby':spec.get('describedby'),'autocomplete':spec.get('autocomplete'),'inputmode':spec.get('inputmode')}
    if 'options' in spec and kind in {'radio','checkbox'}:
        return ''.join(element('label',{},element('input',{'type':kind,'name':spec.get('name'),'value':option['value'],
                       'checked':'' if option.get('checked') else None,'disabled':'' if option.get('disabled') or spec.get('disabled') else None})
                       +element('span',{},escape(option['label']))) for option in spec['options'])
    if kind == 'select':
        return element('select',common,''.join(element('option',{'value':option,'selected':'' if option==spec.get('value') else None},escape(option))
                                               for option in spec.get('options',[])))
    if kind == 'textarea':return element('textarea',{**common,'rows':str(spec.get('rows',3))},escape(spec.get('value','')))
    if kind == 'progress':return element('progress',{'value':str(spec['value']),'max':str(spec['max'])},escape(spec.get('text','')))
    attrs = {**common,'type':'checkbox' if kind=='switch' else kind,'role':'switch' if kind=='switch' else None,
             'placeholder':spec.get('placeholder'),'value':spec.get('value'),'checked':'' if spec.get('checked') else None}
    return element('input',attrs)


def prose(values):
    from .html import element
    chunks = []
    for entry in values:
        if 'paragraph' in entry:chunks.append(element('p',{},inline(entry['paragraph'])))
        elif 'list' in entry:
            value = entry['list']
            chunks.append(element('ol' if value.get('ordered') else 'ul',{},''.join(element('li',{},inline(i)) for i in value['items'])))
        elif 'media' in entry:chunks.append(media(entry['media']))
        else:
            value = entry['quote']
            text = element('p',{},inline(value['text']))
            if value.get('cite'):text += element('cite',{},escape(value['cite']))
            chunks.append(element('blockquote',{},text))
    return ''.join(chunks)


def slot(definition, attrs, value, heading=None):
    from .html import element
    tag = definition.get('content-element', definition['element'])
    if heading is not None:tag = 'h' + str(heading)
    kind, data = value['kind'], value['value']
    if value.get('id'):attrs['id'] = value['id']
    if kind == 'media':
        if tag=='figure':return media(data,attrs)
        return element(tag,attrs,element('img',{'src':data['src'],'alt':data['alt'],'loading':'eager'}))
    if kind == 'placeholder':
        return element(tag if tag not in {'img','ul','ol'} else 'span',{**attrs,'class':'kd-placeholder','role':'img','aria-label':data},escape(data))
    if kind == 'inline':text = inline(data)
    elif kind == 'label':
        attrs['for'] = data['for'];text = inline(data['text'])
    elif kind == 'control':text = control(data)
    elif kind == 'list':text = ''.join(element('li',{},inline(item)) for item in data) if tag in {'ul','ol'} else '<br>'.join(inline(item) for item in data)
    elif kind == 'prose':text = prose(data)
    elif kind == 'links':text = links(data, listed=True, items=tag in {'ul','ol'})
    elif kind == 'actions':
        if tag=='a':return ''.join(element('a',{**attrs,'href':item['href']},escape(item['text'])) for item in data)
        text = links(data)
    elif kind == 'link':
        attrs['href'] = data['href'];text = escape(data['text'])
    elif kind == 'brand':
        attrs['href'] = 'index.html'
        text = (media(data['logo']) if data.get('logo') else '') + element('span',{},escape(data['name']))
    elif kind == 'facts':text = ''.join(element('div',{'data-kd-part':definition.get('fact-part')},element('dt',{},escape(i['label']))+element('dd',{},escape(i['value']))) for i in data)
    elif kind == 'notices':text = ''.join(element('p',{},escape(i)) for i in data)
    elif kind == 'children':text = data  # Only renderer-generated construct bytes, never input HTML.
    else:raise ValueError('Unknown content slot kind: ' + kind)
    return element(tag,attrs,text)
