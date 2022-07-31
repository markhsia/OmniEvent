import copy
import json
import jsonlines
import os
import re

from nltk.tokenize.punkt import PunktSentenceTokenizer
from tqdm import tqdm

from utils import token_pos_to_char_pos, generate_negative_trigger


class Config(object):
    """
    The configurations of this project.
    """
    def __init__(self):
        # The configuration of the data folder.
        self.DATA_FOLDER = "../../../data"

        # The configurations of the training data.
        self.TRAIN_DATA_FOLDER = os.path.join(self.DATA_FOLDER, "tac_kbp_eng_event_nugget_detect_coref_2014-2015/data"
                                                                "/2014/training")
        self.TRAIN_SOURCE_FOLDER = os.path.join(self.TRAIN_DATA_FOLDER, "source")
        self.TRAIN_TOKEN_FOLDER = os.path.join(self.TRAIN_DATA_FOLDER, "token_offset")
        self.TRAIN_ANNOTATION_TBF = os.path.join(self.TRAIN_DATA_FOLDER, "annotation/annotation.tbf")

        # The configurations of the evaluation data.
        self.EVAL_DATA_FOLDER = os.path.join(self.DATA_FOLDER, "tac_kbp_eng_event_nugget_detect_coref_2014-2015/data"
                                                               "/2014/eval")
        self.EVAL_SOURCE_FOLDER = os.path.join(self.EVAL_DATA_FOLDER, "source")
        self.EVAL_TOKEN_FOLDER = os.path.join(self.EVAL_DATA_FOLDER, "token_offset")
        self.EVAL_ANNOTATION_TBF = os.path.join(self.EVAL_DATA_FOLDER, "annotation/annotation.tbf")

        # The configuration of the saving path.
        self.SAVE_DATA_FOLDER = os.path.join(self.DATA_FOLDER, "processed", "TAC-KBP2014")
        if not os.path.exists(self.SAVE_DATA_FOLDER):
            os.mkdir(self.SAVE_DATA_FOLDER)


def read_annotation(ann_file_tbf: str,
                    source_folder: str,
                    token_folder: str):
    """Read the `annotation.tbf` file and save the annotations of event triggers.

    The annotations of the dataset are stored in the `annotation.tbf` file under the `annotation` folder, including the
    trigger word, event type, token-level position, etc. In the `read_annotation()` function, the useful pieces of
    information, including document id and event-related annotations, are extracted and saved to a dictionary. Finally,
    the annotations of each document are stored in a list.

    Args:
        ann_file_tbf: The path of the `annotation.tbf` file.
        source_folder: The path of the folder containing the source text of each document.
        token_folder: The path of the folder containing the correspondence between token-level positions and character-
        level positions of each word.

    Returns:
        A list of dictionaries containing the document id, event ids, event triggers, and token-level positions of each
        document's annotation. The source text of each document is temporarily left blank, which will be extracted in
        the `read_source()` function. For example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp", "text": "",
         "events": [{"type": "Personnel_End-Position",
                     "triggers": [{"id": "E1", "trigger_word": "resign", "position": "t62", "arguments": []}]}, ... ]
         "negative_triggers": [], "entities": []}

        The processed `documents` is then sent to the `read_source()` function for source texts extraction.
    """
    # Initialise the document list.
    documents = list()
    # Initialise the structure of the first document.
    document = {
        "id": str(),
        "text": str(),
        "events": list(),
        "negative_triggers": list(),
        "entities": list()
    }

    # Extract the annotations from annotation.tbf.
    with open(ann_file_tbf) as ann_file:
        for line in tqdm(ann_file, desc="Reading annotation..."):
            # Set the id of the document.
            if line.startswith("#BeginOfDocument"):
                document["id"] = line.strip().split(" ")[-1]
            # Extract the events of the document.
            elif line.startswith("brat_conversion"):
                _, _, event_id, offsets, trigger, event_type, _, _ = line.strip().split("\t")
                event = {
                    "type": event_type,
                    "triggers": [{"id": event_id, "trigger_word": trigger,
                                  "position": offsets, "arguments": list()}]
                }   # Set the position using offsets temporarily, which will be replaced later.
                document["events"].append(event)
            # Initialise the structure for the next document.
            elif line.startswith("#EndOfDocument"):
                documents.append(document)
                document = {
                    "id": str(),
                    "text": str(),
                    "events": list(),
                    "negative_triggers": list(),
                    "entities": list()
                }
            else:
                print("The regulation of %s has not been set." % line)

    return read_source(documents, source_folder, token_folder)


def read_source(documents: list,
                source_folder: str,
                token_folder: str):
    """Extract the source text of each document, delete the xml elements, and replace the position annotations.

    Extract the source text of each document replace the position annotation of each trigger word to character-level
    annotation. The xml annotations (covered by "<>") and the urls (starting with "http") are then deleted from the
    source text, and then the position of each trigger is amended.

    Args:
        documents: A list of dictionaries containing the document id and event trigger annotations.
        source_folder: The path of the folder containing the source text of the documents.
        token_folder: The path of the folder containing the correspondence between token-level positions and character-
        level positions of each token.

    Returns:
        A list of dictionaries containing the document id, source text, and event trigger annotations of each document.
        For example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp", "text": "Shirley Sherrod , we now know that her video ...",
         "events": [{"type": "Personnel_End-Position",
                     "triggers": [{"id": "E1", "trigger_word": "resign", "position": [137, 143], "arguments": []}]},
                     ... ]
         "negative_triggers": [], "entities": []}

        The processed documents` is then sent to the `sentence_tokenize()` function for sentence tokenization.
    """
    for document in tqdm(documents, desc="Reading source..."):
        # Extract the text of each document.
        with open(os.path.join(source_folder, str(document["id"] + ".tkn.txt")),
                  "r") as source:
            document["text"] = source.read()

        # Find the number of xml characters before each character.
        xml_char = list()
        for i in range(len(document["text"])):
            # Retrieve the first i characters of the source text.
            text = document["text"][:i]
            # Delete the <DATETIME> elements from the text.
            text_del = re.sub("<DATETIME>(.*?)< / DATETIME>", " ", text)
            # Delete the xml characters from the text.
            text_del = re.sub("<.*?>", " ", text_del)
            # Delete the unpaired "< / DOC" element.
            text_del = re.sub("< / DOC", " ", text_del)
            # Delete the url elements from the text.
            text_del = re.sub("http(.*?) ", " ", text_del)
            text_del = re.sub("amp;", " ", text_del)
            # Delete some special characters.
            text_del = re.sub("\x92", " ", text_del)
            text_del = re.sub("\x94", " ", text_del)
            text_del = re.sub("\x96", " ", text_del)
            text_del = re.sub("\x97", " ", text_del)
            # Replace the line breaks using spaces.
            text_del = re.sub("\n", " ", text_del)
            # Delete extra spaces within the text.
            text_del = re.sub("\t", " ", text_del)
            text_del = re.sub(" +", " ", text_del)
            # Delete the spaces before the text.
            xml_char.append(len(text_del.lstrip()))

        # Replace the character position of each trigger.
        for event in document["events"]:
            for trigger in event["triggers"]:
                # Case 1: The event trigger only covers one token.
                if len(trigger["position"].split(",")) == 1:
                    with open(os.path.join(token_folder, str(document["id"] + ".txt.tab"))) as offset:
                        for line in offset:
                            token_id, _, token_begin, token_end = line.split("\t")
                            if token_id == trigger["position"]:
                                trigger["position"] = [xml_char[int(token_begin)],
                                                       xml_char[int(token_begin)] + len(trigger["trigger_word"])]
                                # Manually fix an annotation that covers xml elements.
                                if document["id"] == "bolt-eng-DF-170-181122-8808533" and token_id == "t2649":
                                    trigger["position"] \
                                        = [xml_char[13250], xml_char[13250] + len(trigger["trigger_word"])]
                        assert type(trigger["position"]) != str
                # Case 2: The event trigger covers multiple tokens.
                else:
                    # Obtain the start and end token of the trigger.
                    positions = trigger["position"].split(",")
                    start_token, end_token = positions[0], positions[-1]
                    # Replace the token positions to character positions.
                    with open(os.path.join(token_folder, str(document["id"] + ".txt.tab"))) as offset:
                        start_pos, end_pos = -1, -1
                        for line in offset:
                            token_id, _, token_begin, token_end = line.split("\t")
                            if token_id == start_token:
                                start_pos = int(token_begin)
                            elif token_id == end_token:
                                end_pos = int(token_end.strip("\n"))
                        assert start_pos != -1 and end_pos != -1
                        # Slice the trigger word for multiple spans.
                        trigger["trigger_word"] = document["text"][start_pos:end_pos + 1]
                        # Delete the line break within the trigger.
                        trigger["trigger_word"] = re.sub("\n", " ", trigger["trigger_word"])
                        trigger["trigger_word"] = re.sub(" +", " ", trigger["trigger_word"])
                        # Obtain the start and end position of the trigger.
                        trigger["position"] = [xml_char[start_pos], xml_char[start_pos] + len(trigger["trigger_word"])]

        # Delete the <DATETIME> elements from the text.
        document["text"] = re.sub("<DATETIME>(.*?)< / DATETIME>", " ", document["text"])
        # Delete the xml characters from the text.
        document["text"] = re.sub("<.*?>", " ", document["text"])
        # Delete the unpaired "</DOC" element.
        document["text"] = re.sub("< / DOC", " ", document["text"])
        # Delete the url elements from the text.
        document["text"] = re.sub("http(.*?) ", " ", document["text"])
        document["text"] = re.sub("amp;", " ", document["text"])
        # Delete some special characters.
        document["text"] = re.sub("\x92", " ", document["text"])
        document["text"] = re.sub("\x94", " ", document["text"])
        document["text"] = re.sub("\x96", " ", document["text"])
        document["text"] = re.sub("\x97", " ", document["text"])
        # Replace the line breaks using spaces.
        document["text"] = re.sub("\n", " ", document["text"])
        # Delete extra spaces.
        document["text"] = re.sub("\t", " ", document["text"])
        document["text"] = re.sub(" +", " ", document["text"])
        # Delete the spaces before the text.
        document["text"] = document["text"].strip()

        # Fix some annotation errors within the dataset.
        for event in document["events"]:
            for trigger in event["triggers"]:
                if document["text"][trigger["position"][0]:trigger["position"][1]] \
                        != trigger["trigger_word"]:
                    # Manually fix some annotation errors within the dataset.
                    if document["text"][trigger["position"][0]:trigger["position"][1]] == "ant":
                        trigger["position"][0] += len("anti-")
                        trigger["position"][1] += len("anti-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "Ant":
                        trigger["position"][0] += len("Anti-")
                        trigger["position"][1] += len("Anti-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "pro":
                        trigger["position"][0] += len("pro-")
                        trigger["position"][1] += len("pro-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "counter-t":
                        trigger["position"][0] += len("counter-")
                        trigger["position"][1] += len("counter-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "Counter-demons":
                        trigger["position"][0] += len("Counter-")
                        trigger["position"][1] += len("Counter-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "re-elect":
                        trigger["position"][0] += len("re-")
                        trigger["position"][1] += len("re-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "w":
                        trigger["trigger_word"] = "wedding"
                        trigger["position"] = [trigger["position"][0], trigger["position"][0] + len("wedding")]
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "'Wa":
                        trigger["trigger_word"] = "War"
                        trigger["position"] = [trigger["position"][0] + 1, trigger["position"][1] + 1]
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "co-foun":
                        trigger["position"][0] += len("co-")
                        trigger["position"][1] += len("co-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "Non-ele":
                        trigger["position"][0] += len("Non-")
                        trigger["position"][1] += len("Non-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "'Terminall":
                        trigger["trigger_word"] = "Terminally"
                        trigger["position"] = [trigger["position"][0] + 1, trigger["position"][1] + 1]
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "'Battere":
                        trigger["trigger_word"] = "Battered"
                        trigger["position"] = [trigger["position"][0] + 1, trigger["position"][1] + 1]
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "CO-FOUN":
                        trigger["position"][0] += len("CO-")
                        trigger["position"][1] += len("CO-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "post-ele":
                        trigger["position"][0] += len("post-")
                        trigger["position"][1] += len("post-")
                    elif document["text"][trigger["position"][0]:trigger["position"][1]] == "r":
                        trigger["trigger_word"] = "resignation"
                        trigger["position"] = [trigger["position"][0], trigger["position"][0] + len("resignation")]
                    # Delete the annotations that belong to the xml characters.
                    else:
                        event["triggers"].remove(trigger)
                        continue

        # Delete the event if there's no triggers within.
        for event in document["events"]:
            if len(event["triggers"]) == 0:
                document["events"].remove(event)
                continue

    assert check_position(documents)
    return sentence_tokenize(documents)


def sentence_tokenize(documents: list):
    """Tokenize the source text into sentences and match the corresponding event triggers.

    Tokenize the source text into sentences, and match the event triggers that belong to each sentence. The sentences do
    not contain any triggers are stored separately.

    Args:
        documents: A list of dictionaries containing the document id, source text, and the event trigger annotations of
        each document.

    Returns:
        documents_split: A list of dictionaries containing the document id, source text, and the event trigger
        annotations of each sentence within each document. For example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp-1", "text": "And when poor Shirley was forced to resign , ...",
         "events": [{"type": "Personnel_End-Position",
                     "triggers": [{"id": "E1", "trigger_word": "resign", "position": [36, 42], "arguments": []}]},
                     ... ]
         "negative_triggers": [], "entities": []}

        documents_without_event: A list of dictionaries containing the sentences not contain any triggers within. For
        example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp", "sentences": ["'Shirley Sherrod , we now know that ...", ... ]}

        The processed `documents_split` and `documents_without_event` is then sent to the `add_spaces()` function
        for adding spaces beside punctuations.
    """
    # Initialise a list of the splitted documents.
    documents_split, documents_without_event = list(), list()

    for document in tqdm(documents, desc="Tokenizing sentence..."):
        # Initialise the structure for the sentence without event.
        document_without_event = {
            "id": document["id"],
            "sentences": list()
        }

        # Tokenize the sentence of the document.
        sentence_pos, sentence_tokenize = list(), list()
        for start_pos, end_pos in PunktSentenceTokenizer().span_tokenize(document["text"]):
            sentence_pos.append([start_pos, end_pos])
            sentence_tokenize.append(document["text"][start_pos:end_pos])
        sentence_tokenize, sentence_pos = fix_tokenize(sentence_tokenize, sentence_pos)

        # Filter the events for each document.
        for i in range(len(sentence_tokenize)):
            # Initialise the structure of each sentence.
            sentence = {
                "id": document["id"] + "-" + str(i),
                "text": sentence_tokenize[i],
                "events": list(),
                "negative_triggers": list(),
                "entities": list()
            }
            # Filter the events belong to the sentence.
            for event in document["events"]:
                event_sent = {
                    "type": event["type"],
                    "triggers": list()
                }
                for trigger in event["triggers"]:
                    if sentence_pos[i][0] <= trigger["position"][0] < sentence_pos[i][1]:
                        event_sent["triggers"].append(copy.deepcopy(trigger))
                # Modify the start and end positions.
                if not len(event_sent["triggers"]) == 0:
                    for triggers in event_sent["triggers"]:
                        triggers["position"][0] -= sentence_pos[i][0]
                        triggers["position"][1] -= sentence_pos[i][0]
                    sentence["events"].append(event_sent)

            # Append the manipulated sentence into documents.
            if not len(sentence["events"]) == 0:
                documents_split.append(sentence)
            else:
                document_without_event["sentences"].append(sentence["text"])

        # Append the sentence without event into the list.
        if len(document_without_event["sentences"]) != 0:
            documents_without_event.append(document_without_event)

    assert check_position(documents_split)
    return add_spaces(documents_split, documents_without_event)


def add_spaces(documents_split: list,
               documents_without_event: list):
    """Add a space before and after the punctuations.

    Add a space before and after punctuations, such as comma (","), full-stop ("?") and question mark ("?") of the
    source texts. The mention and position of the event trigger annotations are also amended.

    Args:
        documents_split: A list of dictionaries containing the document id and the event trigger annotations of each
        sentence.
        documents_without_event: A list of dictionaries containing the sentences not contain any trigger within.

    Returns:
        documents_split: A list of dictionaries containing the document id and the event trigger annotations of each
        sentence. For example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp-1", "text": "And when poor Shirley was forced to resign , ...",
         "events": [{"type": "Personnel_End-Position",
                     "triggers": [{"id": "E1", "trigger_word": "resign", "position": [36, 42], "arguments": []}]},
                     ... ]
         "negative_triggers": [], "entities": []}

        documents_without_event: A list of dictionaries containing the sentences not contain any triggers within. For
        example:

        {"id": "052fe72e4bb7b33ca69dd0dfd01fc442.cmp", "sentences": ["' Shirley Sherrod , we now know that ...", ... ]}

        The processed `documents_split` and `documents_without_event` are returned as final results.
    """
    for document in tqdm(documents_split, desc="Adding spaces..."):
        punc_char = list()
        for i in range(len(document["text"])):
            # Retrieve the top i characters.
            text = document["text"][:i]
            text_space = re.sub(",", " , ", text)
            text_space = re.sub("\.", " . ", text_space)
            text_space = re.sub(":", " : ", text_space)
            text_space = re.sub(";", " : ", text_space)
            text_space = re.sub("\?", " ? ", text_space)
            text_space = re.sub("!", " ! ", text_space)
            text_space = re.sub("'", " ' ", text_space)
            text_space = re.sub("\"", " \" ", text_space)
            text_space = re.sub("\(", " ( ", text_space)
            text_space = re.sub("\)", " ) ", text_space)
            text_space = re.sub("\[", " [ ", text_space)
            text_space = re.sub("\]", " ] ", text_space)
            text_space = re.sub("\{", " { ", text_space)
            text_space = re.sub("\}", " } ", text_space)
            text_space = re.sub("-", " - ", text_space)
            text_space = re.sub("=", " = ", text_space)
            text_space = re.sub("/", " / ", text_space)
            text_space = re.sub("_", " _ ", text_space)
            text_space = re.sub("\*", " * ", text_space)
            text_space = re.sub("`", " ` ", text_space)
            text_space = re.sub("‘", " ‘ ", text_space)
            text_space = re.sub("’", " ’ ", text_space)
            text_space = re.sub("“", " “ ", text_space)
            text_space = re.sub("”", " ” ", text_space)
            text_space = re.sub("…", " … ", text_space)
            text_space = re.sub(" +", " ", text_space)
            punc_char.append(len(text_space.lstrip()))
        punc_char.append(punc_char[-1])

        document["text"] = re.sub(",", " , ", document["text"])
        document["text"] = re.sub("\.", " . ", document["text"])
        document["text"] = re.sub(":", " : ", document["text"])
        document["text"] = re.sub(";", " ; ", document["text"])
        document["text"] = re.sub("\?", " ? ", document["text"])
        document["text"] = re.sub("!", " ! ", document["text"])
        document["text"] = re.sub("'", " ' ", document["text"])
        document["text"] = re.sub("\"", " \" ", document["text"])
        document["text"] = re.sub("\(", " ( ", document["text"])
        document["text"] = re.sub("\)", " ) ", document["text"])
        document["text"] = re.sub("\[", " [ ", document["text"])
        document["text"] = re.sub("\]", " ] ", document["text"])
        document["text"] = re.sub("\{", " { ", document["text"])
        document["text"] = re.sub("\}", " } ", document["text"])
        document["text"] = re.sub("-", " - ", document["text"])
        document["text"] = re.sub("=", " = ", document["text"])
        document["text"] = re.sub("/", " / ", document["text"])
        document["text"] = re.sub("_", " _ ", document["text"])
        document["text"] = re.sub("\*", " * ", document["text"])
        document["text"] = re.sub("`", " ` ", document["text"])
        document["text"] = re.sub("‘", " ‘ ", document["text"])
        document["text"] = re.sub("’", " ’ ", document["text"])
        document["text"] = re.sub("“", " “ ", document["text"])
        document["text"] = re.sub("”", " ” ", document["text"])
        document["text"] = re.sub("…", " … ", document["text"])
        document["text"] = re.sub(" +", " ", document["text"]).strip()

        for event in document["events"]:
            for trigger in event["triggers"]:
                trigger["position"][0] = punc_char[trigger["position"][0]]
                trigger["position"][1] = punc_char[trigger["position"][1]]
                trigger["trigger_word"] = document["text"][trigger["position"][0]:trigger["position"][1]]
                if trigger["trigger_word"].startswith(" "):
                    trigger["position"][0] += 1
                    trigger["trigger_word"] = document["text"][trigger["position"][0]:trigger["position"][1]]
                if trigger["trigger_word"].endswith(" "):
                    trigger["position"][1] -= 1
                    trigger["trigger_word"] = document["text"][trigger["position"][0]:trigger["position"][1]]

    for document in documents_without_event:
        for i in range(len(document["sentences"])):
            document["sentences"][i] = re.sub(",", " , ", document["sentences"][i])
            document["sentences"][i] = re.sub("\.", " . ", document["sentences"][i])
            document["sentences"][i] = re.sub(":", " : ", document["sentences"][i])
            document["sentences"][i] = re.sub(";", " : ", document["sentences"][i])
            document["sentences"][i] = re.sub("\?", " ? ", document["sentences"][i])
            document["sentences"][i] = re.sub("!", " ! ", document["sentences"][i])
            document["sentences"][i] = re.sub("'", " ' ", document["sentences"][i])
            document["sentences"][i] = re.sub("\"", " \" ", document["sentences"][i])
            document["sentences"][i] = re.sub("\(", " ( ", document["sentences"][i])
            document["sentences"][i] = re.sub("\)", " ) ", document["sentences"][i])
            document["sentences"][i] = re.sub("\[", " [ ", document["sentences"][i])
            document["sentences"][i] = re.sub("\]", " ] ", document["sentences"][i])
            document["sentences"][i] = re.sub("\{", " { ", document["sentences"][i])
            document["sentences"][i] = re.sub("\}", " } ", document["sentences"][i])
            document["sentences"][i] = re.sub("-", " - ", document["sentences"][i])
            document["sentences"][i] = re.sub("=", " = ", document["sentences"][i])
            document["sentences"][i] = re.sub("/", " / ", document["sentences"][i])
            document["sentences"][i] = re.sub("_", " _ ", document["sentences"][i])
            document["sentences"][i] = re.sub("\*", " * ", document["sentences"][i])
            document["sentences"][i] = re.sub("`", " ` ", document["sentences"][i])
            document["sentences"][i] = re.sub("‘", " ‘ ", document["sentences"][i])
            document["sentences"][i] = re.sub("’", " ’ ", document["sentences"][i])
            document["sentences"][i] = re.sub("“", " “ ", document["sentences"][i])
            document["sentences"][i] = re.sub("”", " ” ", document["sentences"][i])
            document["sentences"][i] = re.sub("…", " … ", document["sentences"][i])
            document["sentences"][i] = re.sub(" +", " ", document["sentences"][i]).strip()

    assert check_position(documents_split)
    return documents_split, documents_without_event


def fix_tokenize(sentence_tokenize: list,
                 sentence_pos: list):
    """Fix the wrong sentence tokenizations that affect the event trigger extraction.

    Fix the wrong sentence tokenizations caused by `nltk.tokenize.punkt.PunktSentenceTokenizer` due to points (".")
    existing at the end of abbreviations, which are regarded as the end of a sentence from the sentence tokenization
    algorithm. Fix some wrong tokenizations that split a trigger word into two sentences.

    Args:
        sentence_tokenize: A list of sentences tokenized by `nltk.tokenize.punkt.PunktSentenceTokenizer`.
        sentence_pos: A list of lists containing each sentence's start and end character positions, corresponding to the
        sentences in `sentence_tokenize`.

    Returns:
        new_sentence_tokenize: A list of sentences after fixing the wrong tokenizations.
        new_sentence_pos: A list of lists containing each sentence's start and end character positions, corresponding to
        the sentences in `sentence_tokenize`.
    """
    # Set a list for the deleted indexes.
    del_index = list()

    # Fix the errors in tokenization.
    for i in range(len(sentence_tokenize) - 1, -1, -1):
        if sentence_tokenize[i].endswith("U.S."):
            sentence_tokenize[i] = sentence_tokenize[i] + " " + sentence_tokenize[i + 1]
            sentence_pos[i][1] = sentence_pos[i + 1][1]
            del_index.append(i + 1)

    # Store the undeleted elements into new lists.
    new_sentence_tokenize, new_sentence_pos = list(), list()
    assert len(sentence_tokenize) == len(sentence_pos)
    for i in range(len(sentence_tokenize)):
        if i not in del_index:
            new_sentence_tokenize.append(sentence_tokenize[i])
            new_sentence_pos.append(sentence_pos[i])

    assert len(new_sentence_tokenize) == len(new_sentence_pos)
    return new_sentence_tokenize, new_sentence_pos


def check_position(documents: list) -> bool:
    """Check whether the start and end positions correspond to the event triggers.

    Check whether the string sliced from the source text based on the start and end positions corresponds to the
    event triggers.

    Args:
        documents: A list of dictionaries containing the document id, source text, and event trigger annotations of each
        document/sentence.

    Returns:
        True/False: Returns `False` if an inconsistency is found between the positions and the event trigger; otherwise,
        returns `True`.
    """
    for document in documents:
        for event in document["events"]:
            assert len(document["events"]) != 0
            for trigger in event["triggers"]:
                if document["text"][trigger["position"][0]:trigger["position"][1]] \
                        != trigger["trigger_word"]:
                    return False
    return True


def to_jsonl(filename: str,
             save_dir: str,
             documents: list):
    """Write the manipulated dataset into a jsonl file.

    Write the manipulated dataset into a jsonl file; each line of the jsonl file corresponds to a piece of data.

    Args:
        filename: The filename of the saved jsonl file.
        save_dir: The directory to place the jsonl file.
        documents: The `document_split` or the `document_without_event` dataset.
    """
    label2id = dict(NA=0)
    role2id = dict(NA=0)
    print("We got %d instances" % len(documents))
    for instance in documents:
        for event in instance["events"]:
            event["type"] = ".".join(event["type"].split("_"))
            if event["type"] not in label2id:
                label2id[event["type"]] = len(label2id)
            for trigger in event["triggers"]:
                for argument in trigger["arguments"]:
                    if argument["role"] not in role2id:
                        role2id[argument["role"]] = len(role2id)
    if "train" in filename:
        json.dump(label2id, open(os.path.join(save_dir, "label2id.json"), "w"))
        json.dump(role2id, open(os.path.join(save_dir, "role2id.json"), "w"))
    with jsonlines.open(filename, 'w') as w:
        w.write_all(documents)


if __name__ == "__main__":
    config = Config()

    # Construct the training and evaluation documents.
    train_documents_sent, train_documents_without_event \
        = read_annotation(config.TRAIN_ANNOTATION_TBF, config.TRAIN_SOURCE_FOLDER, config.TRAIN_TOKEN_FOLDER)
    eval_documents_sent, eval_documents_without_event \
        = read_annotation(config.EVAL_ANNOTATION_TBF, config.EVAL_SOURCE_FOLDER, config.EVAL_TOKEN_FOLDER)

    # Save the documents into jsonl files.
    all_train_data = generate_negative_trigger(train_documents_sent, train_documents_without_event)
    json.dump(all_train_data, open(os.path.join(config.SAVE_DATA_FOLDER, 'train.json'), "w"), indent=4)
    to_jsonl(os.path.join(config.SAVE_DATA_FOLDER, 'train.unified.jsonl'), config.SAVE_DATA_FOLDER, all_train_data)

    all_test_data = generate_negative_trigger(eval_documents_sent, eval_documents_without_event)
    json.dump(all_test_data, open(os.path.join(config.SAVE_DATA_FOLDER, 'test.json'), "w"), indent=4)
    to_jsonl(os.path.join(config.SAVE_DATA_FOLDER, 'test.unified.jsonl'), config.SAVE_DATA_FOLDER, all_test_data)
