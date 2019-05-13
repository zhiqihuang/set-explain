import json, sys, os, re
import argparse
import bisect
import spacy
import threading

"""
break document level json to sentence level json

"""

def merge_task(task_list, args):
	nlp = spacy.load("en_core_web_sm")

	for fname in task_list:
		outputname = 'SENTENCE_{}'.format(fname.split('_')[1])
		context = []

		with open('{}/{}'.format(args.input_dir,fname), 'r') as f:
			doc = f.readlines()
		f.close()

		for item in doc:
			item_dict = json.loads(item)
			title = item_dict['title']
			did = item_dict['did']
			pid = item_dict['pid']
			doc = nlp(item_dict['text'])
			sid = 0
			for s in doc.sents:
				sent_json = {}
				sent_json['title'] = title
				sent_json['did'] = did
				sent_json['pid'] = pid
				sent_json['sid'] = sid
				sent_json['text'] = s.text
				sid += 1
				context.append(json.dumps(sent_json))
		
		with open('{}/{}'.format(args.output_dir, outputname), "w+") as f:
			f.write('\n'.join(context))
		f.close()

def split(a, n):
	k, m = divmod(len(a), n)
	return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

def main():
	parser = argparse.ArgumentParser(description="Keep json format and clean text ")
	parser.add_argument('--input_dir', type=str, default='', help='json document directory')
	parser.add_argument('--output_dir', type=str, default='', help='output directory')
	parser.add_argument('--num_process', type=int, default=2, help='number of parallel')
	
	args = parser.parse_args()

	input_dir = os.listdir(args.input_dir)
	tasks = list(split(input_dir, args.num_process))

	threads = []
	for i in range(args.num_process):
		t = threading.Thread(target=merge_task, args=(tasks[i], args, ))
		threads.append(t)
		t.start()

if __name__ == '__main__':
	main()
	