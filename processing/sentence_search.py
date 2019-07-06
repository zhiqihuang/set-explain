import json, sys, os, re
import argparse
import bisect
import nltk
import multiprocessing as mp
from tqdm import tqdm

"""
search sentence based on keywords

"""

def merge_task(task_list, args):
    keywords = set(args.keywords.split(','))
    for fname in task_list:
        outputname = '{}_{}'.format(args.output_prefix,fname)
        context = []

        with open('{}/{}'.format(args.input_dir,fname), 'r') as f:
            doc = f.readlines()
        f.close()

        for item in tqdm(doc, desc='{}'.format(fname), mininterval=30):
            item_dict = json.loads(item)
            entity_text = set([em['text'] for em in item_dict['entityMentions']])
            if entity_text.intersectionn(keywords) == keywords:
                context.append(item_dict['tokens'])
        
        if context != []:
            with open('{}/{}'.format(args.output_dir, outputname), "w+") as f:
                f.write('\n'.join(context))
            f.close()

def split(a, n):
    k, m = divmod(len(a), n)
    return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

def main():
    parser = argparse.ArgumentParser(description="search sentence based on keywords")
    parser.add_argument('--input_dir', type=str, default='', help='autophrase parsed directory')
    parser.add_argument('--output_dir', type=str, default='', help='output directory')
    parser.add_argument('--output_prefix', type=str, default='', help='output filename')
    parser.add_argument('--keywords', type=str, default='', help='search keywords')
    parser.add_argument('--num_process', type=int, default=2, help='number of parallel')
    
    args = parser.parse_args()

    input_dir = os.listdir(args.input_dir)
    tasks = list(split(input_dir, args.num_process))

    processes = [mp.Process(target=merge_task, args=(tasks[i], args)) for i in range(args.num_process)]

    for p in processes:
        p.start()

    for p in processes:
        p.join()

if __name__ == '__main__':
    main()
    