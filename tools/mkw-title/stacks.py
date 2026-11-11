import re,collections,sys
R=sys.argv[1]; names=sys.argv[2].split(',') if len(sys.argv)>2 else ['precise','offcpu']
threads=sys.argv[3].split(',') if len(sys.argv)>3 else ['GPU','VulkanWorker','GPUFencingThread','CPUCore_0','CPUCore_1','eboot.bin']
depth=int(sys.argv[4]) if len(sys.argv)>4 else 3
for name in names:
    agg=collections.defaultdict(collections.Counter); tot=collections.Counter()
    for line in open(R+f'/{name}.folded'):
        stack,_,n=line.rstrip().rpartition(' '); n=int(n)
        frames=stack.split(';'); comm=frames[0].rsplit('-',1)[0]
        tot[comm]+=n
        fr=[re.sub(r'\(.*','',f) for f in frames[1:] if not re.match(r'(sub_380|clock_gettime|_nanosleep|sub_[0-9a-f]+|thread_start|pthread_\w+|void\* std::__1::__thread_proxy.*)$',f)]
        key=' <- '.join(f[:70] for f in fr[-depth:][::-1]) if fr else '?'
        agg[comm][key]+=n
    print('#####',name)
    for comm in threads:
        print('==',comm,tot[comm])
        for k,v in agg[comm].most_common(16): print('  %6d %5.1f%%  %s'%(v,100.0*v/max(1,tot[comm]),k))
