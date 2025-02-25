import os
from pathlib import Path
import sys
sys.path.append("../../../")
import logging
import torch 

import json

from transformers import set_seed, EarlyStoppingCallback

from OmniEvent.arguments import DataArguments, ModelArguments, TrainingArguments, ArgumentParser
from OmniEvent.backbone.backbone import get_backbone
from OmniEvent.model.model import get_model

from OmniEvent.input_engineering.input_utils import get_plain_label
from OmniEvent.input_engineering.seq2seq_processor import EAESeq2SeqProcessor, type_start, type_end

from OmniEvent.evaluation.metric import compute_seq_F1
from OmniEvent.evaluation.dump_result import get_duee_submission_s2s
from OmniEvent.evaluation.convert_format import get_ace2005_argument_extraction_s2s

from OmniEvent.evaluation.utils import predict, get_pred_s2s

from OmniEvent.trainer_seq2seq import Seq2SeqTrainer, ConstrainedSeq2SeqTrainer


# argument parser
parser = ArgumentParser((ModelArguments, DataArguments, TrainingArguments))
if len(sys.argv) == 2 and sys.argv[1].endswith(".json"):
    model_args, data_args, training_args = parser.parse_json_file(json_file=os.path.abspath(sys.argv[1]))
elif len(sys.argv) >= 2 and sys.argv[1].endswith(".yaml"):
    model_args, data_args, training_args = parser.parse_yaml_file(yaml_file=os.path.abspath(sys.argv[1]))
else:
    model_args, data_args, training_args = parser.parse_args_into_dataclasses()

# output dir
model_name_or_path = model_args.model_name_or_path.split("/")[-1]
output_dir = Path(training_args.output_dir, training_args.task_name, model_args.paradigm,
                  f"{model_name_or_path}-{model_args.aggregation}")
output_dir.mkdir(exist_ok=True, parents=True)
training_args.output_dir = output_dir


# logging config 
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
)

# prepare labels
role2id_path = data_args.role2id_path
data_args.role2id = {get_plain_label(k): v for k, v in json.load(open(role2id_path)).items()}
training_args.label_name = ["labels"]

# used for evaluation
training_args.role2id = data_args.role2id
data_args.id2role = {id: role for role, id in data_args.role2id.items()}


# markers 
dataset_markers = ["<ace>", "<duee>", "<fewfc>", "<kbp>", "<ere>", "<maven>", "<leven>"]
data_args.markers = ["<event>", "</event>", type_start, type_end] + dataset_markers

# logging
logging.info(data_args)
logging.info(model_args)
logging.info(training_args)

# set seed
set_seed(training_args.seed)

# writter 
earlystoppingCallBack = EarlyStoppingCallback(early_stopping_patience=training_args.early_stopping_patience,
                                              early_stopping_threshold=training_args.early_stopping_threshold)

# model 
backbone, tokenizer, config = get_backbone(model_args.model_type, model_args.backbone_checkpoint_path,
                                           model_args.model_name_or_path, data_args.markers,
                                           new_tokens=data_args.markers)
model = get_model(model_args, backbone)
if training_args.pipeline:
    gpu_numbers = torch.cuda.device_count()
    num_per_gpus = int(24 / gpu_numbers)
    device_map = {i : [j for j in range(num_per_gpus * i, num_per_gpus * (i + 1))] for i in range(gpu_numbers)}
    model.parallelize(device_map)
print(gpu_numbers)

data_class = EAESeq2SeqProcessor
metric_fn = compute_seq_F1

# dataset 
train_dataset = data_class(data_args, tokenizer, data_args.train_file, data_args.train_pred_file, True)
eval_dataset = data_class(data_args, tokenizer, data_args.validation_file, data_args.validation_pred_file, False)

# set event types
training_args.data_for_evaluation = eval_dataset.get_data_for_evaluation()

# Trainer 
trainer = Seq2SeqTrainer(
    args=training_args,
    model=model,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    compute_metrics=metric_fn,
    data_collator=train_dataset.collate_fn,
    tokenizer=tokenizer,
    callbacks=[earlystoppingCallBack],
    # decoding_type_schema={"role_list": all_roles_except_na}
)

trainer.save_model(training_args.output_dir)