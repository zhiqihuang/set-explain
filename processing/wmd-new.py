import json, sys, os, re
import argparse
import bisect
import multiprocessing as mp
from multiprocessing import Pool
import collections
from tqdm import tqdm
import spacy
import wmd
from itertools import product
from itertools import combinations
import phrasemachine

def sent_search(params):
    (task_list, args) = params

    nlp = spacy.load('en_core_web_lg', disable=['ner'])

    query = args.query_string.split(',')

    freq = dict()

    for ent in query:
        freq.update({ent:{'total':0}})

    context = dict((ent,[]) for ent in query)

    for fname in task_list:

        with open('{}/{}'.format(args.input_dir,fname), 'r') as f:
            doc = f.readlines()
        f.close()

        for item in tqdm(doc, desc='{}'.format(fname), mininterval=10):
            try:
                item_dict = json.loads(item)
            except:
                print(fname, item)
                sys.stdout.flush()
                continue

            for ent in query:
                if ent not in item_dict['nsubj']:
                    continue
                else:
                    doc = nlp(item_dict['text'])
                    if len(doc) >= 40:
                        continue
                    tokens = [token.text for token in doc]
                    pos = [token.pos_ for token in doc]
                    phrases = phrasemachine.get_phrases(tokens=tokens, postags=pos)
                    item_dict['phrases'] = list(phrases['counts'])
                    context[ent].append(item_dict)

                    freq[ent]['total'] += 1
                    if item_dict['did'] in freq[ent]:
                        freq[ent][item_dict['did']] += 1
                    else:
                        freq[ent].update({item_dict['did']:1})
                    # #item_dict['core'] = ' '.join([token.text for token in doc if token.is_stop == False])
                    # tokens = [token.text for token in doc]
                    # pos = [token.pos_ for token in doc]
                    # phrases = phrasemachine.get_phrases(tokens=tokens, postags=pos)
                    # item_dict['doc_score'] = count_results[ent][item_dict['did']]/count_results[ent]['total']
                    # item_dict['phrases'] = list(phrases['counts'])
                    # context[ent].append(item_dict)
    
    return {'context':context, 'freq':freq}

def cooccur_cluster(params):
    (cooccur, entityMentioned, query) = params
    nlp = spacy.load('en_core_web_lg', disable=['ner'])
    nlp.add_pipe(wmd.WMD.SpacySimilarityHook(nlp), last=True)
    context = {}
    for keyent in cooccur:
        
        sentsPool = []
        for seed in query:
            sentsPool.append(entityMentioned[seed][keyent]['sents']['text'])

        index_list = [range(len(s)) for s in sentsPool]
        best_wmd = 1e6
        best_pair = []
        prod = list(product(*index_list))
        if len(prod) > 1e5:
            continue
        for pair in tqdm(prod, desc='wmd-{}'.format(keyent), mininterval=10):
            sentsPair = [sentsPool[index][pair[index]] for index in range(len(pair))]

            comb = combinations(sentsPair, 2) 
            current_wmd = 0
            for group in comb:
                doc1 = nlp(group[0])
                doc2 = nlp(group[1])
                current_wmd += doc1.similarity(doc2)

            if current_wmd < best_wmd:
                best_wmd = current_wmd
                best_pair = sentsPair
        
        context.update({keyent:{'best_pair':best_pair, 'best_wmd':best_wmd}})
    
    return context

def split(a, n):
    k, m = divmod(len(a), n)
    return (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

def main():
    parser = argparse.ArgumentParser(description="group sentence by cooccurrence")
    parser.add_argument('--input_dir', type=str, default='', help='autophrase parsed directory')
    parser.add_argument('--query_string', type=str, default='', help='search query')
    parser.add_argument('--num_process', type=int, default=2, help='number of parallel')
    
    args = parser.parse_args()
    query = args.query_string.split(',')

    print(query)
    sys.stdout.flush()

    ##### sentence search #####
    input_dir = os.listdir(args.input_dir)
    tasks = list(split(input_dir, args.num_process))
    
    inputs = [(tasks[i], args) for i in range(args.num_process)]

    with Pool(args.num_process) as p:
        search_results = p.map(sent_search, inputs)
    
    search_merge = search_results[0]['context']
    count_merge = search_results[0]['freq']

    for pid in range(1, len(search_results)):
        tmp_context = search_results[pid]['context']
        tmp_freq = search_results[pid]['freq']
        for ent in query:
            search_merge[ent] += tmp_context[ent]
            count_merge[ent]['total'] += tmp_freq[ent]['total']
            tmp_freq[ent].pop('total', None)
            count_merge[ent].update(tmp_freq[ent])
    
    for ent in query:
        for index in range(len(search_merge[ent])):
            search_merge[ent][index]['doc_score'] = count_merge[ent][search_merge[ent][index]['did']]/count_merge[ent]['total']

    # for ent in query:
    #     for sent in search_merge[ent]:
    #         print(sent)
    # sys.stdout.flush()

    fid = 1
    for ent in query:
        with open('retrieved-{}.txt'.format(fid), "w+") as f:
            for sent in search_merge[ent]:
                f.write(json.dumps(sent) + '\n')
        f.close()
        fid += 1

    # threshold = int(0.3 * len(cooccur))

    # cooccur_subset = [item[0] for item in cooccur_sorted[:threshold]]

    ##### wmd based on cooccurrence #####
    # tasks = list(split(list(cooccur), args.num_process))
    # inputs = [(tasks[i], entityMentioned, query) for i in range(args.num_process)]
    
    # with Pool(args.num_process) as p:
    #     wmd_results = p.map(cooccur_cluster, inputs)

    # wmd_merge = wmd_results[0]
    # for pid in range(1, len(wmd_results)):
    #     tmp_res = wmd_results[pid]
    #     wmd_merge.update(tmp_res)

    # sorted_wmd = sorted(wmd_merge.items(), key=lambda x : x[1]['best_wmd'])

    # for item in sorted_wmd:
    #     print(item)
    # sys.stdout.flush()

if __name__ == '__main__':
    main()