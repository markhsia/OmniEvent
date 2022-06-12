"""
@ File:    LDC2015E68_sent.py
@ Author:  Zimu Wang
# Update:  June 10, 2022
@ Purpose: Convert the LDC2015E68 dataset in sentence level.
"""
import copy
import re
import jsonlines
import os
import json 

from nltk.tokenize.punkt import PunktSentenceTokenizer
from xml.dom.minidom import parse
from tqdm import tqdm 

from utils import token_pos_to_char_pos, generate_negative_trigger


class Config(object):
    """
    The configurations of this project.
    """
    def __init__(self):
        # The configuration for the project (current) folder.
        self.PROJECT_FOLDER = "../../../data"

        # The configurations for the data.
        self.DATA_FOLDER = os.path.join(self.PROJECT_FOLDER, 'LDC2015E68/data')
        self.GOLD_FOLDER = os.path.join(self.DATA_FOLDER, 'ere')
        self.SOURCE_FOLDER = os.path.join(self.DATA_FOLDER, 'source')

        # The configuration for the saving path.
        self.SAVE_DATA_FOLDER = os.path.join(self.PROJECT_FOLDER, 'LDC2015E68/LDC2015E68')

        if not os.path.exists(self.SAVE_DATA_FOLDER):
            os.mkdir(self.SAVE_DATA_FOLDER)


def read_xml(gold_folder, source_folder):
    """
    Read the annotated files and construct the hoppers.
    :param gold_folder:   The path for the gold_standard folder.
    :param source_folder: The path for the source folder.
    :param mode:          The mode of the task, train/eval.
    :return: documents:   The set of the constructed documents.
    """
    # Initialise the document list.
    documents = list()

    # List all the files under the gold_standard folder.
    gold_files = os.listdir(gold_folder)
    # Construct the document of each annotation data.
    for gold_file in tqdm(gold_files):
        # Initialise the structure of a document.
        document = {
            'id': str(),
            'text': str(),
            'events': list(),
            'negative_triggers': list(),
            'entities': list()
        }

        # Parse the data from the xml file.
        dom_tree = parse(os.path.join(gold_folder, gold_file))
        # Set the id (filename) as document id.
        document['id'] = dom_tree.documentElement.getAttribute('doc_id')

        # Extract the entities from the xml file.
        entities = dom_tree.documentElement.getElementsByTagName('entities')[0] \
                                           .getElementsByTagName('entity')
        for entity in entities:
            # Initialise a dictionary for each entity.
            entity_dict = {
                'type': entity.getAttribute('type'),
                'mentions': list(),
            }
            # Extract the mentions within each entity.
            mentions = entity.getElementsByTagName('entity_mention')
            for mention in mentions:
                # Delete the url elements from the mention.
                entity_mention = mention.getElementsByTagName('mention_text')[0].childNodes[0].data.split(' ')
                mention_dict = {
                    'id': mention.getAttribute('id'),
                    'mention': ' '.join([word for word in entity_mention if
                                         not (word.startswith('&lt;') or word.endswith('&gt;'))]),
                    'position': [int(mention.getAttribute('offset')),
                                 int(mention.getAttribute('offset')) + len(' '.join(entity_mention))]
                }
                entity_dict['mentions'].append(mention_dict)
            document['entities'].append(entity_dict)

        # Extract the fillers from the xml file.
        fillers = dom_tree.documentElement.getElementsByTagName('fillers')[0] \
                                          .getElementsByTagName('filler')
        for filler in fillers:
            # Initialise a dictionary for each filler.
            filler_mention = filler.childNodes[0].data.split(' ')
            filler_dict = {
                'type': filler.getAttribute('type'),
                'mentions': [
                    {'id': filler.getAttribute('id'),
                     'mention': ' '.join([word for word in filler_mention if
                                          not (word.startswith('&lt;') or word.endswith('&gt;'))]),
                     'position': [int(filler.getAttribute('offset')),
                                  int(filler.getAttribute('offset')) + len(' '.join(filler_mention))]}]
                }
            document['entities'].append(filler_dict)

        # Extract the hoppers from the xml file.
        hoppers = dom_tree.documentElement.getElementsByTagName('hoppers')[0] \
                                          .getElementsByTagName('hopper')
        for hopper in hoppers:
            # Initialise a dictionary for each hopper.
            hopper_dict = {
                'type': hopper.getElementsByTagName('event_mention')[0]
                              .getAttribute('subtype'),
                'triggers': list()
            }
            # Extract the mentions within each hopper.
            mentions = hopper.getElementsByTagName('event_mention')
            # Extract the triggers from each mention.
            for mention in mentions:
                trigger = mention.getElementsByTagName('trigger')[0]
                trigger_word = trigger.childNodes[0].data.split(' ')
                trigger_dict = {
                    'id': mention.getAttribute('id'),
                    'trigger_word': ' '.join([word for word in trigger_word if
                                              not (word.startswith('&lt;') or word.endswith('&gt;'))]),
                    'position': [int(trigger.getAttribute('offset')),
                                 int(trigger.getAttribute('offset')) + len(' '.join(trigger_word))],
                    'arguments': list()
                }
                hopper_dict['triggers'].append(trigger_dict)
                # Extract the arguments for each trigger.
                arguments = mention.getElementsByTagName('em_arg')
                for argument in arguments:
                    # Classify the type of the argument (entity/filler).
                    if argument.getAttribute('entity_id') == '':
                        arg_id = argument.getAttribute('filler_id')
                    else:
                        arg_id = argument.getAttribute('entity_id')
                    # Initialise a flag for whether the entity id exists.
                    flag = 0
                    # Justify whether the argument being added.
                    for added_argument in trigger_dict['arguments']:
                        if arg_id == added_argument['id'] and argument.getAttribute('role') == added_argument['role']:
                            argument_mention = argument.childNodes[0].data.split(' ')
                            argument_dict = {
                                'mention': ' '.join([word for word in argument_mention if
                                                     not (word.startswith('&lt;') or word.endswith('&gt;'))]),
                                'position': -1
                            }
                            # Classify the type of the argument (entity/filler).
                            if argument.getAttribute('entity_mention_id') == '':
                                mention_id = argument.getAttribute('filler_id')
                            else:
                                mention_id = argument.getAttribute('entity_mention_id')
                            # Match the position of the argument.
                            for entity in document['entities']:
                                for entity_mention in entity['mentions']:
                                    if entity_mention['id'] == mention_id:
                                        argument_dict['position'] = entity_mention['position']
                            added_argument['mentions'].append(argument_dict)
                            flag = 1
                    # Initialise a new dictionary if the entity id not exists.
                    # The id of the argument will be deleted later.
                    if flag == 0:
                        argument_mention = argument.childNodes[0].data.split(' ')
                        argument_dict = {
                            'id': arg_id,
                            'role': argument.getAttribute('role'),
                            'mentions': [{'mention': ' '.join([word for word in argument_mention if
                                                               not (word.startswith('&lt;') or word.endswith('&gt;'))]),
                                          'position': -1}]
                        }
                        # Classify the type of the argument (entity/filler).
                        if argument.getAttribute('entity_mention_id') == '':
                            mention_id = argument.getAttribute('filler_id')
                        else:
                            mention_id = argument.getAttribute('entity_mention_id')
                        # Match the position of the argument.
                        for entity in document['entities']:
                            for entity_mention in entity['mentions']:
                                if entity_mention['id'] == mention_id:
                                    argument_dict['mentions'][0]['position'] = entity_mention['position']
                        trigger_dict['arguments'].append(argument_dict)
                # Delete the id of each argument.
                for argument in trigger_dict['arguments']:
                    del argument['id']
                document['events'].append(hopper_dict)

        # Delete the id of each entity.
        for entity in document['entities']:
            for mention in entity['mentions']:
                del mention['id']
        documents.append(document)

    return read_source(documents, source_folder)


def read_source(documents, source_folder):
    """
    Extract the source texts from the corresponding file.
    :param documents:     The structured documents list.
    :param source_folder: Path of the source folder.
    :return documents:    The list of the constructed documents.
    """
    for document in tqdm(documents):
        # Extract the sentence of each document.
        with open(os.path.join(source_folder, (document['id'] + '.cmp.txt')), 'r') as source:
            document['text'] = source.read()

        # Find the number of xml characters before each character.
        xml_char = list()
        for i in range(len(document['text'])):
            # Retrieve the top i characters.
            text = document['text'][:i]
            # Find the length of the text after deleting the
            # xml elements and line breaks before the current index.
            # Delete the <DATETIME> elements from the text.
            text_del = re.sub('<DATETIME>(.*?)< / DATETIME>', ' ', text)
            # Delete the xml characters from the text.
            text_del = re.sub('<.*?>', ' ', text_del)
            # Delete the unpaired '</DOC' element.
            text_del = re.sub('</DOC', ' ', text_del)
            # Delete the url elements from the text.
            text_del = re.sub('http(.*?) ', ' ', text_del)
            # Replace the line breaks using spaces.
            text_del = re.sub('\n', ' ', text_del)
            # Delete extra spaces within the text.
            text_del = re.sub(' +', ' ', text_del)
            # Delete the spaces before the text.
            xml_char.append(len(text_del.lstrip()))

        # Delete the <DATETIME> elements from the text.
        document['text'] = re.sub('<DATETIME>(.*?)< / DATETIME>', ' ', document['text'])
        # Delete the xml characters from the text.
        document['text'] = re.sub('<.*?>', ' ', document['text'])
        # Delete the unpaired '</DOC' element.
        document['text'] = re.sub('</DOC', ' ', document['text'])
        # Delete the url elements from the text.
        document['text'] = re.sub('http(.*?) ', ' ', document['text'])
        # Replace the line breaks using spaces.
        document['text'] = re.sub('\n', ' ', document['text'])
        # Delete extra spaces within the text.
        document['text'] = re.sub(' +', ' ', document['text'])
        # Delete the spaces before the text.
        document['text'] = document['text'].strip()

        # Subtract the number of xml elements and line breaks.
        for event in document['events']:
            for trigger in event['triggers']:
                if not document['text'][trigger['position'][0]:trigger['position'][1]] \
                       == trigger['trigger_word']:
                    trigger['position'][0] = xml_char[trigger['position'][0]]
                    trigger['position'][1] = xml_char[trigger['position'][1]]
                # for argument in trigger['arguments']:
                #     for event_mention in argument['mentions']:
                #         event_mention['position'][0] = xml_char[event_mention['position'][0]]
                #         event_mention['position'][1] = xml_char[event_mention['position'][1]]
        for entity in document['entities']:
            for entity_mention in entity['mentions']:
                if not document['text'][entity_mention['position'][0]:entity_mention['position'][1]] \
                       == entity_mention['mention']:
                    entity_mention['position'][0] = xml_char[entity_mention['position'][0]]
                    entity_mention['position'][1] = xml_char[entity_mention['position'][1]]

        # Fix some annotation errors.
        for event in document['events']:
            for trigger in event['triggers']:
                if not document['text'][trigger['position'][0]:trigger['position'][1]] \
                        == trigger['trigger_word']:
                    trigger['trigger_word'] = re.sub('<.*?>', '', trigger['trigger_word'].strip())
                for argument in trigger['arguments']:
                    for mention in argument['mentions']:
                        if document['text'][mention['position'][0]:mention['position'][1]] \
                                != mention['mention']:
                            mention['mention'] = re.sub('<.*?>', '', mention['mention'].strip())
            for entity in document['entities']:
                for mention in entity['mentions']:
                    if not document['text'][mention['position'][0]:mention['position'][1]] \
                            == mention['mention']:
                        mention['mention'] = re.sub('<.*?>', '', mention['mention'].strip())

    return clean_documents(documents)


def clean_documents(documents):
    """
    Delete the entities and arguments in the xml elements.
    :param documents:         The structured documents list.
    :return: documents_clean: The cleaned documents list.
    """
    # Initialise the structure for the cleaned documents.
    documents_clean = list()

    # Clean the documents with correct elements.
    for document in documents:
        # Initialise the structure for the cleaned document.
        document_clean = {
            'id': document['id'],
            'text': document['text'],
            'events': list(),
            'negative_triggers': list(),
            'entities': list()
        }

        # Save the entities not in the xml elements.
        for entity in document['entities']:
            entity_clean = {
                'type': entity['type'],
                'mentions': list()
            }
            for mention in entity['mentions']:
                if document_clean['text'][mention['position'][0]:mention['position'][1]] \
                       == mention['mention']:
                    entity_clean['mentions'].append(mention)
            if len(entity_clean['mentions']) != 0:
                document_clean['entities'].append(entity_clean)

        # Save the events and the cleaned arguments.
        for event in document['events']:
            event_clean = {
                'type': event['type'],
                'triggers': list()
            }
            for trigger in event['triggers']:
                trigger_clean = {
                    'id': trigger['id'],
                    'trigger_word': trigger['trigger_word'],
                    'position': trigger['position'],
                    'arguments': list()
                }
                for argument in trigger['arguments']:
                    argument_clean = {
                        'role': argument['role'],
                        'mentions': list()
                    }
                    for mention in argument['mentions']:
                        if document_clean['text'][mention['position'][0]:mention['position'][1]] \
                                == mention['mention']:
                            argument_clean['mentions'].append(mention)
                        if len(argument_clean['mentions']) != 0:
                            trigger_clean['arguments'].append(argument_clean)
                event_clean['triggers'].append(trigger_clean)
            document_clean['events'].append(event_clean)
        documents_clean.append(document_clean)

    assert check_position(documents_clean)
    return sentence_tokenize(documents_clean)


def sentence_tokenize(documents):
    """
    Tokenize the document into multiple sentences.
    :param documents:         The structured documents list.
    :return: documents_split: The split sentences' document.
    """
    # Initialise a list of the splitted documents.
    documents_split = list()
    documents_without_event = list()

    for document in documents:
        # Initialise the structure for the sentence without event.
        document_without_event = {
            'id': document['id'],
            'sentences': list()
        }

        # Tokenize the sentence of the document.
        sentence_pos = list()
        sentence_tokenize = list()
        for start_pos, end_pos in PunktSentenceTokenizer().span_tokenize(document['text']):
            sentence_pos.append([start_pos, end_pos])
            sentence_tokenize.append(document['text'][start_pos:end_pos])
        sentence_tokenize, sentence_pos = fix_tokenize(sentence_tokenize, sentence_pos)

        # Filter the events for each document.
        for i in range(len(sentence_tokenize)):
            # Initialise the structure of each sentence.
            sentence = {
                'id': document['id'] + '-' + str(i),
                'text': sentence_tokenize[i],
                'events': list(),
                'negative_triggers': list(),
                'entities': list()
            }
            # Filter the events belong to the sentence.
            for event in document['events']:
                event_sent = {
                    'type': event['type'],
                    'triggers': list()
                }
                for trigger in event['triggers']:
                    if sentence_pos[i][0] <= trigger['position'][0] < sentence_pos[i][1]:
                        trigger_sent = {
                            'id': trigger['id'],
                            'trigger_word': trigger['trigger_word'],
                            'position': copy.deepcopy(trigger['position']),
                            'arguments': list()
                        }
                        for argument in trigger['arguments']:
                            argument_sent = {
                                'role': argument['role'],
                                'mentions': list()
                            }
                            for mention in argument['mentions']:
                                if sentence_pos[i][0] <= mention['position'][0] < sentence_pos[i][1]:
                                    argument_sent['mentions'].append(copy.deepcopy(mention))
                            if not len(argument_sent['mentions']) == 0:
                                trigger_sent['arguments'].append(argument_sent)
                        event_sent['triggers'].append(trigger_sent)
                # Modify the start and end positions.
                if not len(event_sent['triggers']) == 0:
                    for trigger in event_sent['triggers']:
                        if not sentence['text'][trigger['position'][0]:trigger['position'][1]] \
                                == trigger['trigger_word']:
                            trigger['position'][0] -= sentence_pos[i][0]
                            trigger['position'][1] -= sentence_pos[i][0]
                        for argument in trigger['arguments']:
                            for mention in argument['mentions']:
                                if not sentence['text'][mention['position'][0]:mention['position'][1]] \
                                       == mention['mention']:
                                    mention['position'][0] -= sentence_pos[i][0]
                                    mention['position'][1] -= sentence_pos[i][0]
                    sentence['events'].append(event_sent)
            # Filter the entities belong to the sentence.
            for entity in document['entities']:
                entity_sent = {
                    'type': entity['type'],
                    'mentions': list()
                }
                for mention in entity['mentions']:
                    if sentence_pos[i][0] <= mention['position'][0] < sentence_pos[i][1]:
                        entity_sent['mentions'].append(copy.deepcopy(mention))
                if not len(entity_sent['mentions']) == 0:
                    for mention in entity_sent['mentions']:
                        mention['position'][0] -= sentence_pos[i][0]
                        mention['position'][1] -= sentence_pos[i][0]
                    sentence['entities'].append(entity_sent)

            # Append the manipulated sentence into the list of documents.
            if not (len(sentence['events']) == 0 or len(sentence['entities']) == 0):
                documents_split.append(sentence)
            else:
                document_without_event['sentences'].append(sentence['text'])

        # Append the sentence without event into the list.
        if len(document_without_event['sentences']) != 0:
            documents_without_event.append(document_without_event)

    assert check_position(documents_split)
    return documents_split, documents_without_event


def fix_tokenize(sentence_tokenize, sentence_pos):
    """
    Fix the wrong tokenization within a sentence.
    :param sentence_pos:      List of starting and ending position of each sentence.
    :param sentence_tokenize: The tokenized sentences list.
    :return: The fixed sentence position and tokenization lists.
    """
    # Set a list for the deleted indexes.
    del_index = list()

    # Fix the errors in tokenization.
    for i in range(len(sentence_tokenize) - 1, -1, -1):
        if sentence_tokenize[i].endswith('U.S.') or sentence_tokenize[i].endswith('U.N.') \
                or sentence_tokenize[i].endswith('U.K.') or sentence_tokenize[i].endswith('St.') \
                or sentence_tokenize[i].endswith('Jan.') or sentence_tokenize[i].endswith('Feb.') \
                or sentence_tokenize[i].endswith('Aug.') or sentence_tokenize[i].endswith('Sept.') \
                or sentence_tokenize[i].endswith('Oct.') or sentence_tokenize[i].endswith('Nov.') \
                or sentence_tokenize[i].endswith('Dec.') or sentence_tokenize[i].endswith('$75-80k/yr.') \
                or sentence_tokenize[i].endswith('Dr.') or sentence_tokenize[i].endswith('B.A.') \
                or sentence_tokenize[i].endswith('Lt.') or sentence_tokenize[i].endswith('Ft.') \
                or sentence_tokenize[i].endswith('weed.') or sentence_tokenize[i].endswith('Mr.') \
                or sentence_tokenize[i].endswith('No.') or sentence_tokenize[i].endswith('p.m.'):
            if i not in del_index:
                sentence_tokenize[i] = sentence_tokenize[i] + ' ' + sentence_tokenize[i + 1]
                sentence_pos[i][1] = sentence_pos[i + 1][1]
            else:
                sentence_tokenize[i - 1] = sentence_tokenize[i - 1] + ' ' + sentence_tokenize[i]
                sentence_pos[i - 1][1] = sentence_pos[i][1]
            del_index.append(i)

    # Store the undeleted elements into new lists.
    new_sentence_tokenize = list()
    new_sentence_pos = list()
    assert len(sentence_tokenize) == len(sentence_pos)
    for i in range(len(sentence_tokenize)):
        if i not in del_index:
            new_sentence_tokenize.append(sentence_tokenize[i])
            new_sentence_pos.append(sentence_pos[i])

    assert len(new_sentence_tokenize) == len(new_sentence_pos)
    return new_sentence_tokenize, new_sentence_pos


def check_position(documents):
    """
    Check whether the position of each trigger is correct.
    :param documents: The set of the constructed documents.
    :return: True/False
    """
    for document in documents:
        # Check the positions of the events.
        for event in document['events']:
            for trigger in event['triggers']:
                if document['text'][trigger['position'][0]:trigger['position'][1]] \
                        != trigger['trigger_word']:
                    return False
                for argument in trigger['arguments']:
                    for mention in argument['mentions']:
                        if document['text'][mention['position'][0]:mention['position'][1]] \
                                != mention['mention']:
                            return False
        # Check the positions of the entities.
        for entity in document['entities']:
            for mention in entity['mentions']:
                if document['text'][mention['position'][0]:mention['position'][1]] \
                        != mention['mention']:
                    return False
    return True


def to_jsonl(filename, documents):
    """
    Write the manipulated dataset into jsonl file.
    :param filename:  Name of the saved file.
    :param documents: The manipulated dataset.
    :return:
    """
    with jsonlines.open(filename, 'w') as w:
        w.write_all(documents)


if __name__ == '__main__':
    config = Config()

    # Construct the documents of the dataset.
    documents_sent, documents_without_events = read_xml(config.GOLD_FOLDER, config.SOURCE_FOLDER)

    # Save the documents into jsonl file.
    all_data = generate_negative_trigger(documents_sent, documents_without_events)
    json.dump(all_data, open(os.path.join(config.SAVE_DATA_FOLDER, 'data.json'), "w"), indent=4)
    to_jsonl(os.path.join(config.SAVE_DATA_FOLDER, 'data.unified.jsonl'), all_data)
