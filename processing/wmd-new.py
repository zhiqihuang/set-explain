import json, sys, os, re
import argparse
import bisect
import multiprocessing as mp
from multiprocessing import Pool
import collections
from tqdm import tqdm
import spacy
import textacy
import numpy as np
import wmd
from nltk.tokenize import MWETokenizer
from nltk.corpus import stopwords
import nltk
from itertools import product
from itertools import combinations
import phrasemachine
from scipy.stats import skew
stop = set(stopwords.words('english'))

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

            entity_text = set([em for em in item_dict['entityMentioned']])

            for ent in query:
                if ent not in entity_text:
                    continue
                else:
                    doc = nlp(item_dict['text'])
                    if len(doc) >= 30:
                        continue
                    unigram = [token.text for token in textacy.extract.ngrams(doc,n=1,filter_nums=True, filter_punct=True, filter_stops=True)]
                    item_dict['unigram'] = unigram
                    context[ent].append(item_dict)

                    freq[ent]['total'] += 1
                    if item_dict['did'] in freq[ent]:
                        freq[ent][item_dict['did']] += 1
                    else:
                        freq[ent].update({item_dict['did']:1})
    
    return {'context':context, 'freq':freq}

def cooccur_cluster(params):
    (cooccur, entityMentioned, query) = params
    nlp = spacy.load('en_core_web_lg', disable=['ner'])
    nlp.add_pipe(wmd.WMD.SpacySimilarityHook(nlp), last=True)
    context = {}
    for keyent in cooccur:
        
        sentsPool = []
        for seed in query:
            sentsPool.append(entityMentioned[seed][keyent])

        index_list = [range(len(s)) for s in sentsPool]
        best_wmd = 1e6
        best_pair = []
        prod = list(product(*index_list))
        if len(prod) > 1e5:
            continue
        for pair in tqdm(prod, desc='wmd-{}'.format(keyent), mininterval=10):
            sentsPair = [sentsPool[index][pair[index]]['text'] for index in range(len(pair))]

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
    nlp = spacy.load('en_core_web_lg', disable=['ner']) 
    nlp.max_length = 10000000

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

    fid = 1
    for ent in query:
        with open('retrieved-{}.txt'.format(fid), "w+") as f:
            for sent in search_merge[ent]:
                f.write(json.dumps(sent) + '\n')
        f.close()
        fid += 1

    unigrams = []
    for ent in query:
        context = ' '.join([sent['text'] for sent in search_merge[ent]])
        doc = nlp(context)
        unigram = set([token.text for token in textacy.extract.ngrams(doc,n=1,filter_nums=True, filter_punct=True, filter_stops=True, min_freq=5)])
        unigrams.append(unigram)

    unigram_set = unigrams[0]
    for item in unigrams:
        unigram_set = unigram_set.union(item)

    for ent in query:
        unigram_set.discard(ent)

    unigram_sents = {}
    for ent in query:
        unigram_sents.update({ent:{}})  
        for sent in search_merge[ent]:
            unigram = set(sent['unigram'])
            unigram_intersect = unigram.intersection(unigram_set)
            for item in unigram_intersect:
                if item in unigram_sents[ent].keys():
                    unigram_sents[ent][item].append(sent)
                else:
                    unigram_sents[ent].update({item:[sent]})

    score_dist = {}
    for ug in unigram_set:
        score_dist.update({ug:{}})
        for ent in query:
            score_dist[ug].update({ent:0})
            if ug in unigram_sents[ent].keys():
                did = set()
                for sent in unigram_sents[ent][ug]:
                    score_dist[ug][ent] += sent['doc_score']
                    #if sent['did'] not in did:
                        #score_dist[ug][ent] += sent['doc_score']
                    did.add(sent['did'])

    agg_score = {}
    for ug in score_dist.keys():
        tmp_res = [item[1] for item in score_dist[ug].items()]
        agg_score.update({ug: np.mean(tmp_res) - np.std(tmp_res)})


    score_sorted = sorted(agg_score.items(), key=lambda x: x[1], reverse=True)

    for item in score_sorted[:100]:
        print(item, score_dist[item[0]])
    sys.stdout.flush()

    context = ''
    for ent in query:
        context += ' '.join([item['text'] for item in search_merge[ent]])

    mined_phrases = phrasemachine.get_phrases(context, minlen=2,maxlen=8)

    tokenizer = MWETokenizer(separator=' ')

    for e in unigram_set:
        tokenizer.add_mwe(nltk.word_tokenize(e))
    
    list_phrases = set(mined_phrases['counts'])
    phrases_score = {}
    for phrase in tqdm(list_phrases, desc='phrase-eval', mininterval=10):
        score = 0
        tokens = nltk.word_tokenize(phrase)
        nonstop_tokens = [token for token in tokens if token not in stop]
        if len(nonstop_tokens) / len(tokens) <= 0.5:
            continue
        raw_tokenized = tokenizer.tokenize(tokens)
        tokenized_set = set(raw_tokenized)
        for token in tokenized_set.intersection(unigram_set):
            score += agg_score[token]
        phrases_score.update({phrase:score/len(nonstop_tokens)})

    phrases_sorted = sorted(phrases_score.items(), key=lambda x: x[1], reverse=True)

    print(phrases_sorted[:10])


    ##### wmd based on cooccurrence #####
    # tasks = list(split(list(unigram_set), args.num_process))
    # inputs = [(tasks[i], unigram_sents, query) for i in range(args.num_process)]
    
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