#!/usr/bin/python3
"""Root-owned release installer, invoked by the restricted deployment SSH account.

Uploaded data is an artifact, not a root shell script. Runtime secrets stay on host.
"""
import base64,fcntl,hashlib,hmac,json,os,pwd,re,shutil,subprocess,sys,tarfile,tempfile,time,urllib.request,zipfile
from pathlib import Path
from decimal import Decimal
import yaml

BASE=Path('/srv/matrix-prp/releases')
STATE=Path('/var/lib/matrix-prp-deploy')
BACKUPS=Path('/root/prp-deploy-backups')
CONFIG=Path('/etc/matrix-prp/application.yml')
JAVA='/usr/lib/jvm/java-21-openjdk-amd64/bin/java'
SERVICE='matrix-prp'
try:ACCOUNT=pwd.getpwnam('openclaw')
except KeyError:ACCOUNT=None  # Artifact boundary tests also run on GitHub-hosted Linux.

def log(message):print(message,flush=True)
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def sql(query,db='matrix_prp'):
 if not re.fullmatch(r'[a-zA-Z0-9_]+',db):raise ValueError('Invalid database')
 cmd=['docker','exec','-i','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot -N -B '+db]
 return subprocess.check_output(cmd,input=query.encode()).decode().strip()
def dump(path):
 with path.open('wb') as out:
  run(['docker','exec','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --default-character-set=utf8mb4 -uroot --single-transaction --routines --triggers --events --no-tablespaces matrix_prp'],stdout=out)
def restore(path,db):
 with path.open('rb') as inp:
  run(['docker','exec','-i','matrix-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --default-character-set=utf8mb4 -uroot '+db],stdin=inp)
def schema_version(db='matrix_prp'):
 if sql("SHOW TABLES LIKE 'flyway_schema_history';",db)!='flyway_schema_history':return 7
 value=sql("SELECT version FROM flyway_schema_history WHERE success=1 AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1;",db)
 return int(value)

# Reviewed V15 from 067c6df; exact SQL SHA256: 98f0e9b8c5754d6337edd6605b57906c99a304058e9ef442af1daa080c97b531
V15_PUBLIC_FOOD_SIGNATURES=frozenset('''
00441cea00fe6923d2912e56eefe853eb940a709f3e8d347cd618b04dd33ed3f
005923749437a4b58132a8e3fbab0182087745363f83d75abaa417b292fa6d82
00d44b321f0fa64b40756ae9ddb0fc51e3645eb6a6c52389443339896927be4a
03b5f6946c507a8afd3b4730553e13c2fda16c2635aab543348758681bdf014d
0aacfb6bd9324602a2ca95c6f9b64453ece4381e3fde0c1724905285bd469a07
0ec166aa65c9ceba4e363d078704b3ebb3f03ad111a6ef4ac7d31dea48dd414a
0f0d4936af379ad418af7be8d171d0abce5a52964ffe64a6571052e28cf28ba0
114517c99ed0616fa94fa2c2cbf1c2354ef447251344501df57cfddb5db3c50b
12111db4d6eb4a2e9cedd584c85a13eec2cea3aa7c14859acfdc1237d71822cb
149f4d4badef32e85007103cf22e9fa7a53586c1b5232c5ac2fcfbfd0bb5c89d
1b8a2cde9d9683126ef685689fbd32203694747809eaccbf92e64176669451ce
1c3434a8c42e9c2600defc75234bf446a356bd54800799671c96c0579dc5d80f
1c9f496cfb89d1aa636b65e6ddac53565c656c85911b366a2d59d920831d447c
1ce995faed488555ad5907eec8a7af0aff9d262a8bded5bbae84d587159b2a49
1f119cb43b73d0332c809de4efaa97296fe5df0293b7a866a4b7d8923f5534d7
213593cb4d8273e51496e89d93d320e11bf0be9a601d1c0ec0e3b2ae620ffbc7
2296c309b6a0242b672d78648a423dc1a65de67ea3aa0e679e850ed9a2e09280
2408a13b97a5100002dfda2dca6362e6d2412a2b6afd122f05e2c3ecd4e2f5d0
24f1f6fb55998ac275af0738e65498126df80dfaf187eff02755157067e9b4cc
26f83eb5dfc77672baaabe9366a13e61e9af4a883a243c07a0f5ca5a4f021ba8
27d8e912751da6f7feee3521bc8037b6fca78d1c83c74345098c693080936823
28942008b3001282dc99210e6bf7af78e004698760c2b73f0d0a4798cd73d1d4
2a34e782ef9c560310416e030323314eff607ee2b861553645db55fdf5292296
31f438985110ceb7ba713c44db6ea68b441a82065632772d11f9314eebb329e9
32bfd21bf505da5b97d292cc774519f39206da0c277794bad88ecc54010b3e8c
335bb0c32cf682feeb34c757b8105553d857749a9188442a72fad6bc6f82144e
359f069960e024d00f5501f084459b0a69a53095cab475e3e6e1398b6913b402
397e321bd35afd27a2653aa5855a203a9bfe2c0592d56371c9d493139067412f
39922dce51898f4a0b0d53ff574d8e81c3faea6f2bd33024d3351b931144c2bb
3a5da03107fdc7c9f9118f0c05681b78b3985b78e19f49396d3d46e8496d2a68
3cdeb34e0a21b1198b62583a7eeff99e3feabd0a6609874820e5c87f8e2b5423
3d45fdb4a6bf23658ab5223f7f14b38099228142d0271dba4fa261fe617648e7
412473d7232c93572b27e14528103e9c4ab8350cbccf71def3bd5ea1315b49f0
44b3eb5d8a89b7aef25cd5ac8523e4f2ce4d3ed774676c2cbb707447bc7c4576
4755f7362f0d0236a40efa2870ef0bbe19df607db54a1225cb8acdfe4d1f100c
4a7b852dd818c48df639f6990ac0691fdc9e5ca6a6bb9b628b67efb393f383f0
4a93048b2d9b45dda98f6bc7cbaab5a343262d13374fdbda221a5a70e08651b6
4ba38cb6a5d0dbb0f42e7482030c4a2791d331909c22c1da39165a869a543001
4bc047998144e6712d64c0bb0cd70d1480414d344b67abef79865f97d6b2cf7d
508349e6811524513971eb02a36198b71c84cfd759e50e123fe9b7bbe9d63f53
514b1e6a3d912cd12f3d8d5322947b0201e6e62005889de1a831dae177cb48d2
525ca32fcb8b0d67d1ec86afd6e6bc769dce2bba503b35ee8074882d29653525
54dbe88ac140ef0ea16cfb8d527b9305844cbca2c928775161287837e2755630
55b43dec1432fbc8357c27b36bcfabc00e8e39da816aa19a7fe811051fb1d556
5621c8224c77761680cb308f2f1e701cfafefc75d447959fdb86ffcf2b719ad6
573513fcfa8ee197e236e731b39952a4f39a5e229d55043b8f4044ebdb80ec3c
57a8615d9dfb675fd76a40fa6b510e0794e4a5c378dfebd0d74d6dbddb4edc97
5af8da5391bdc9d0e082f19d9d96572386629aae8b015fd3109afda420a0305b
5c392cdb624bbf20774c081192fdc9939211115a87bd0dc6b7888104603de537
5eefc5543a9beabccab7865c5cc3de2e7f62b0d3b4f2e1c66a36b51aff63dd6b
5fb60ea4e3f82c5770b9dfcd1809347deabb64d503c0226aa84e721681d7415c
62846e0efac360028e920311f7034d4a3309d8460a1a7d3d57639a7ddd853825
6650acdc26dc7d36c1f25e5e4d4a2b59da5670cde8524720c4792c02b429f3a6
66af8f780cdc2b0958f45ad8f6ff11e652557ee7befc83c46fab9689be2be0d9
677cea1b4ea7ce2e0638404a3009cd06bd76d87024e79066ef00a86609297762
691809e4b6d08b0acc9fd0a9e86e8c3fb495da9d7c8cc5e12376c6c948cbc42f
6aa57c553b61691ab408d40bc65238f5600071aedd3955a3324f7498cf7e933b
6ce7b93c28bb032f967bdf99ad76edc930a80a32be9207a6c338b6573e5f29b8
6dc7df8d02e63283a43e219ce911a56292d79d1f23be0d12add7c5ae0a287f13
6e25dabfcdac0d5ddaa6a066140e808b9d2cc5d6a74c8af4f17987cf37306bc0
70647448ba1225d65be6951ad780739d84e163df97d6672aff91940bcc943f88
71e1dbdfffcce19c02916045b0a76dcdbaddc73b89a0e5887e55f0af1a5fb643
74f11471501a04bfd362cfccf8c9f5da35fdcad58ff9a215fa5fd82a8b854fbb
75f3bef67553fbbdeb87d62f1e6e8b0d8da36268180b2020f7e3fb6da3c65d73
774e55370dba246ea43dd4d34bd6f8a6c2db4f90fe6709a9bd5fd14049d1565d
77e33b59397427d6362087be1f3fb3096394745050cf05acb62102e8bdaed3ce
795a5420798b55b7f3f34e6a866b34d8744d23ee5dea8f63c3890cfaea72ebf2
7bdeb1383bc407804e84faff39a0a58decb01d187d2ba9949a42d2033038d8bb
7d513b4c3d694025b196da490ff28fbef141366892f7b639160b0917dff31e2d
815c1aea43f38ad94b38a358314fd2828fbe764310a88aeb6f2742eaceda8e85
81bcc5627c7fccb20a11d46fc4c44344b712c78867b7077379e82542afcde3c5
82c3bf4b1835cc73da652c4ebd4d82f61e9a28be535db978b3dfb452c1f5214f
83d7b5826d38ed34d151fd16085fdfea2427d98d225c17fa49c907c6997b4a25
88164c3e10a6bdb230c66b84cac3b627757ddbf30097cc7904240d1421ae8e5a
8ae1765499adf61a60738c0a7d3ce8e6d296454f8bb8e7b4c3484dc369ce631f
8b57df417a63c75976eca577811e94d53d548a2723563c8a5c8727a44cdc3371
8b869df71952d5ba79f89b309a67492ecd50f6834774ef87b727c3017b8b079a
92005a6eb28d9d69a0b565f8170cdd52e669eeb64cded63eb334e39986cc818b
93f6a510b01a2d7b429f82c7e5103ebdae612813c83ea59378f4ca2c65d4c68c
95dc3388c2ca3bdf649970f9ddfe571175f3c50efb1d73ef3d82f6793d309fb4
96ee69b53acb559552efad260b2214b4ac45386e402cbe03d89697e01bb837dd
978b22d37874e2a6026ba0b7eaf70f494f76a5074813a82c479a698c7c65ab50
994ca9802d5b914501fe37d2f6405da7df3cc0b2f6c697c149263a50826fd837
99c4810168d80b799ff67862d9a49d5461bbfa7d7fbf5feb11c300397de23a11
9bee5a206e113ce6b2968a539188655180cc5eb6b5b5e922deb80f5af48f9672
9dac743b4dd2653a51bd33d3948e92a98fe1d87b06dcba75ef675e5eeea8e8d4
9e16d59052ddf7b09e221417d5d1983e4d3c1365a695c1dbfa62642a38668231
9e794e4dd23a93b9918f1ac1aa3f8575dc5bd62bace80debd829e8dd482337ec
a169ae22bdf43eee15dbf8c0570bedbb8210639428707890f4392cd1ab4da884
a33dfd8108fcea5e0c2cd3e6b1057e6b09fc9f11bd608b3c538159082c8da6ef
a33f8b90a92fa9034f773f42360a6797f27c983188486e76c546a0a0e8910add
a3565f324537c30730795faed7e6604ae2e621345340ece23e673642ee92debb
a60869b0a69d942a6908e3c99d76e971180ffc51c94f104de6ce7ff8c7726dde
a87b3849b7c74279b5a00fdcf7f1dadbf9f26d40e3fcebdd949c09a1f46c6633
aa96f8c32232682e77ce0204020aacb092ebfab07d9cccb4debc5750fa0d8740
adf29273717c059a3b357eee6033e3b29e57f54241bf4f4d45bbebf9bedd0895
afa7c9dffb84fa02dbfd875369383623b7e56bc90aed4aed5dd330c8c33e0ebd
b17df97794d88b6da5378cd3d7027bdef4f31644d3d4f0606a9e790f6ae7f1ac
b4b693a3c60568f5d6b1bbe99abf94e90558d3c1acbbf3884bd69ef890213448
b4cd895247862bd108fbaa4def1f3dc3c16b2c01dfd9d0ad73e587242d3a27fc
b4d0ddee608e6f228751af1e7727836d359a465edc164ed077cf496a707c93fe
b641c2231c40397d39736e38bdad392f5be01c4c55d947944f149642fc3269b8
b8981cd39312d34e9653665133cbc44f0c5f8cac046a02d20ae90583071bf1f2
b9767efc4efc790b9541f396dba84c7509d8b54840db2cf82e8e42e93ce8a086
bd49e416819387beb7851a4a7064b91f09a205e873417e3cd53347a8d23242c8
c0a758f1005ac2774269d0a20849043995c640ac74d97cea95a18e1bb815dee4
c123f112dc2c4aca9bcc4e7f883851b8a911aa64616ff8f514fccebdcd3cbe82
ca63c2ef144b533d7ed3b2d0863d73890f2712ed095ed137330c6d95a0c58df8
cac44436f2fac95df4da4b5f9de98db923e4e2901bcfe95babd5e3701cd270d6
cbdb0029e93d3a8403ce31087be912912baf9d9b35838abdd0a6a1210d55ae07
cc452101a510023660c714a67b3187a99dd2756c9ea4a12a9ef62123a9276128
cc4dc379a3e4db57c5135c238b06e314e3d68ac9e45be8e2073b68d02eb2a6e5
cd2bc81e3045d20babdfbcf58043c54675f5157a40e6097886df52be5d2b43ae
cd7c8b1451eaa388a8bf989daa7d390e60f2f7e066998dbabed1b94fc897ce10
ce247cba89104a900a7ff8968798d57090aad7b8e0cba1ec5c12933470161108
cf807b9ae4218a2dca09b32e41acdbbf7eeb1d3b8335f3767ca97423fe2b221e
d24dde806dff9a36514fb944c6e335702ebb2f93c13ebf66fb9d51e2987e722e
d2ee94222ea0ce533400234273b507397b8d92ccf5ac35a563d78862dc4d90c6
d32cb01aee6f6da10a761f4f761d9288be801c1896786aeae651dd3dd47d0d6b
d3f20cf9e004515e84844a9cc63485b8fb51e0bdb975d8715b5ff17922e9cd38
db9e9b8d6d5c6ea9a73577e1d39ef4ab4e875cc7f9431e01f201ae2825a2fbe8
df08b999edb3fb5fb51da3196ef2b45d2f9c3b4b5bedd24eb5d018fc0a96711f
e2980586a11c1e6995da15879f6d85c2cdb8a58de638f44f4ada08351ee54eaf
e41c019350b83ad908a93d74941f69aee58ffa127e493322a65e6e1c6a743614
e50ae9fab35a89239dc5b48727a8c1ab36ad6842515ab03bf90c20d93927c15f
e67b109b781cbff0bbdd17d91f439fe8d22fe72d8b6fc0c51b33f8571f6378bc
e6d5ce69eb9f1a74748fd0bb7fd6a692c5c87873d9c3cb9b15c93f3b1396f893
e756bccb40d72a3827eb237ce3275d3297dcb383d7df2e1e0b399e664e345a7c
e82e1982892bc73b2a66d6033522c0fc569dbe1ef32e0d677c05bb42a113feef
e86262375218afc98f01b9130cfaa5ff19d2cef7a6e30d6370c675ca983b6cfc
e87ba784872896d2122d5f6a30e985c6c03f85fa16739dfce2c97091fc10c1bd
ea4c238bf066bc87e43d80ffb358366afb2a2c0406d88687ea8610d8bbd084c3
ea4e128a729371a12f6923b2c0dc4d1eef10dbaa51ebaece32edf09922ab2747
eba3358a20990e38d552e71b4728cf5114f14f218f09edd7e9df658fb71113e2
ed4482e319eab0278cf208dfb823561d477682aab2cad495931cd1b90cf62241
efd362dfb4c803bfa4091e470a9f0486bb0c5e079a8778bb73c5b197e1fd04b3
efe08c34a73c69f54692e1f17a630ebe0d5993e58c9127e88ce03e17a6f2cdec
f30c8015cd7719ef49d836f084657b504ecd268e422bad9f700af6229f52b4e9
f7926f93e6dd79cd71e81d0d438d26bc168ee0f0ae2f413b990415ed9df03fa9
f9a5214e40fd56cebfba64081016129b86de820d67c8ca976ac08b3d1c1b4919
fb18160da58037e85d64d0fae2e38a14f7a91b8ba805dd25c5830add9613b0aa
fda99bc996b8ea9fa21abea8fba709c0a0e0357d2a3fc84d1c99be55c54ce5aa
fefce66a45eb94b500267fabffae76dd3ab64cf99c599318a6ef143cdf411357
'''.split())

def sql_identifier(name):
 if not re.fullmatch(r'[A-Za-z0-9_]+',name):raise ValueError('Unexpected SQL identifier')
 return '`'+name+'`'

def snapshot(db='matrix_prp',schema_evidence=False):
 tables=sql('SHOW TABLES;',db).splitlines()
 counts={};integrity={}
 for table in tables:
  if table=='flyway_schema_history':continue
  quoted=sql_identifier(table)
  columns=[r.split('\t')[0] for r in sql('SHOW COLUMNS FROM '+quoted+';',db).splitlines()]
  primary=sql("SELECT column_name FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='"+table+"' AND constraint_name='PRIMARY' ORDER BY ordinal_position;",db).splitlines()
  if not primary:raise ValueError('Cannot protect table without a primary key: '+table)
  key='HEX(JSON_ARRAY('+','.join(map(sql_identifier,primary))+'))'
  body='HEX(JSON_ARRAY('+','.join(map(sql_identifier,columns))+'))'
  fingerprints={}
  for row in sql('SELECT '+key+','+body+' FROM '+quoted+' ORDER BY '+','.join(map(sql_identifier,primary))+';',db).splitlines():
   pk,encoded=row.split('\t')
   if pk in fingerprints:raise ValueError('Duplicate primary key in snapshot')
   fingerprints[pk]=hashlib.sha256(encoded.encode('ascii')).hexdigest()
  counts[table]=int(sql('SELECT COUNT(*) FROM '+quoted+';',db))
  if len(fingerprints)!=counts[table]:raise ValueError('Incomplete table snapshot: '+table)
  integrity[table]=fingerprints
 # JSON+HEX handles tabs/newlines/NULL safely; no raw food or personal rows enter logs/backups.
 foods={};identities={}
 if 'prp_wellness_foods' in counts:
  q='SELECT HEX(JSON_ARRAY(id)),HEX(JSON_ARRAY(owner_user_id,name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)) FROM prp_wellness_foods ORDER BY id;'
  for line in sql(q,db).splitlines():
   pk,encoded=line.split('\t');values=json.loads(bytes.fromhex(encoded),parse_float=Decimal)
   canonical=[values[1],values[2],*[format(Decimal(str(v)),'.2f') for v in values[3:7]],values[7]]
   digest=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
   foods[pk]=digest if values[0] is None else None
   identities[pk]=hashlib.sha256(json.dumps(values[1:3],ensure_ascii=False).encode()).hexdigest() if values[0] is None else None
  if set(foods)!=set(integrity['prp_wellness_foods']):raise ValueError('Incomplete food metadata snapshot')
 backfill=None
 if 'prp_wellness_ai_action_targets' in counts:
  # V19 adds links only for exact durable meal idempotency keys and the same owner.
  expected=sql("SELECT HEX(JSON_ARRAY(d.id,d.user_id,CASE WHEN m.idempotency_key=d.id THEN 0 ELSE CAST(SUBSTRING(m.idempotency_key,38) AS UNSIGNED) END,'meal',m.id)) FROM prp_wellness_ai_drafts d JOIN prp_wellness_meals m ON m.user_id=d.user_id WHERE d.status='CONSUMED' AND (m.idempotency_key=d.id OR (m.idempotency_key LIKE CONCAT(d.id,'-%') AND SUBSTRING(m.idempotency_key,38) REGEXP '^[0-9]+$'));",db).splitlines()
  actual=sql('SELECT HEX(JSON_ARRAY(draft_id,user_id,ordinal,target_type,record_id)) FROM prp_wellness_ai_action_targets;',db).splitlines()
  digest=lambda rows:hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()
  backfill={'expected_count':len(expected),'actual_count':len(actual),
            'expected_sha256':digest(expected),'actual_sha256':digest(actual)}
 videos=sql('SELECT id,user_id,folder_id,storage_key,size_bytes,HEX(title) FROM prp_video_assets ORDER BY id;',db)
 result={'counts':counts,'videos':hashlib.sha256(videos.encode()).hexdigest(),
         'row_sha256':integrity,'public_food_signature':foods,'public_food_identity':identities,'v19_backfill':backfill}
 if schema_evidence:
  result['table_definitions']={t:hashlib.sha256(re.sub(r' AUTO_INCREMENT=\d+','',sql('SHOW CREATE TABLE `'+t+'`;',db)).encode()).hexdigest() for t in result['counts']}
 return result

def schema_fingerprint(db='matrix_prp'):
 definitions=[]
 for table in sql('SHOW TABLES;',db).splitlines():
  if table!='flyway_schema_history':definitions.append(re.sub(r' AUTO_INCREMENT=\d+','',sql('SHOW CREATE TABLE `'+table+'`;',db)))
 return hashlib.sha256('\n'.join(definitions).encode()).hexdigest()
def assert_preserved(before,after,new_empty_tables=()):
 if new_empty_tables:
  assert set(before.get('table_definitions',{}))==set(before['counts']),'Missing original DDL evidence'
  assert set(after.get('table_definitions',{}))==set(after['counts']),'Missing current DDL evidence'
  for table in before['counts']:
   assert before['table_definitions'][table]==after['table_definitions'][table],('Historical table structure changed',table)
 for table,count in before['counts'].items():
  actual=after['counts'].get(table,-1)
  if table=='prp_wellness_foods':assert actual>=count,(table,count,actual)
  else:assert actual==count,(table,count,actual)
  original=before.get('row_sha256',{}).get(table)
  current=after.get('row_sha256',{}).get(table)
  assert isinstance(original,dict) and isinstance(current,dict),('Missing row integrity evidence',table)
  assert len(original)==count and len(current)==actual,('Incomplete row integrity evidence',table)
  for pk,digest in original.items():
   assert current.get(pk)==digest,('Historical row changed or deleted',table,pk)
  if table=='prp_wellness_foods':
   old_seeds=before.get('public_food_signature',{})
   new_seeds=after.get('public_food_signature',{})
   assert set(old_seeds)==set(original) and set(new_seeds)==set(current),'Missing food metadata'
   old_ids=before.get('public_food_identity',{});new_ids=after.get('public_food_identity',{})
   assert set(old_ids)==set(original) and set(new_ids)==set(current),'Missing food identities'
   added=set(current)-set(original);seen=set(old_seeds.values());seen_ids=set(old_ids.values())
   for pk in added:
    signature=new_seeds[pk]
    assert signature in V15_PUBLIC_FOOD_SIGNATURES,('Unexpected or private new food',pk)
    assert signature not in seen,('Duplicate public food seed',pk)
    assert new_ids[pk] is not None and new_ids[pk] not in seen_ids,('Duplicate public food identity',pk)
    seen.add(signature);seen_ids.add(new_ids[pk])
 # V16 only adds an initially empty per-user AI draft table; reject unreviewed objects.
 added_tables=set(after['counts'])-set(before['counts'])
 assert added_tables<= {'prp_wellness_ai_drafts','prp_wellness_dish_templates','prp_ai_conversation_meta','prp_wellness_ai_action_targets','prp_vocal_takes','prp_finance_import_batches','prp_finance_import_rows','prp_finance_source_links'} | set(new_empty_tables),'Unexpected new business table'
 assert set(new_empty_tables)<=added_tables,'Declared new table already existed or was not created'
 for table in added_tables:
  if table=='prp_wellness_ai_action_targets':
   proof=after.get('v19_backfill')
   assert isinstance(proof,dict),'Missing V19 backfill proof'
   assert proof['actual_count']==after['counts'][table]==proof['expected_count'],'Unexpected V19 backfill count'
   assert proof['actual_sha256']==proof['expected_sha256'],'Unexpected V19 backfill content or ownership'
  else:assert after['counts'][table]==0,('Unexpected records in new table',table)
 assert before['videos']==after['videos'],'Video ownership or records changed'

# BEGIN VERSIONED MIGRATION POLICY
"""Bounded additive-empty-table contracts; also embedded in the root controller.

Trust remains the existing authorized publisher and protected-main workflow.
Hashes bind the reviewed contract to SQL/commit; they are not human signatures.
Unsupported SQL, modes, versions or evidence fail closed.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

MIGRATION_POLICY_BASE = 21
MIGRATION_POLICY_LIMIT = 262144


def migration_policy_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate migration policy key')
        result[key] = value
    return result


def migration_policy_load(data):
    if len(data) > MIGRATION_POLICY_LIMIT: raise ValueError('Migration policy too large')
    return json.loads(data, object_pairs_hook=migration_policy_unique)


def migration_policy_sql_tables(data):
    """Conservative lexical reader, deliberately narrower than MySQL DDL."""
    text = data.decode('utf-8')
    if '\\' in text or '/*' in text or '*/' in text:
        raise ValueError('SQL escapes/block comments require specialist review')
    tokens = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == '#' or (text.startswith('--', i) and (i+2 == len(text) or text[i+2].isspace())):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end+1
            tokens.append(' ')
        elif char in "'\"`":
            quote = char
            start = i
            i += 1
            while i < len(text):
                if text[i] == quote:
                    if i+1 < len(text) and text[i+1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else: raise ValueError('Unclosed SQL quote')
            # Backticks are identifiers; quoted strings are not SQL keywords.
            tokens.append(text[start:i] if quote == '`' else "'literal'")
        else:
            tokens.append(char)
            i += 1
    clean = ''.join(tokens)
    statements = clean.split(';')
    if statements[-1].strip(): raise ValueError('Terminated CREATE TABLE statements required')
    tables = []
    for statement in statements[:-1]:
        statement = statement.strip()
        match = re.match(r'CREATE\s+TABLE\s+`?(prp_[a-z][a-z0-9_]{0,58})`?\s*\(', statement, re.I)
        if not match: raise ValueError('Only explicit CREATE TABLE prp_* is supported')
        table = match[1]
        if table != table.lower() or table in tables: raise ValueError('Duplicate/noncanonical new table')
        body_start = match.end()
        depth = 1
        pos = body_start
        quoted_identifier = False
        while pos < len(statement) and depth:
            char = statement[pos]
            if char == '`': quoted_identifier = not quoted_identifier
            if not quoted_identifier:
                if char == '(': depth += 1
                if char == ')': depth -= 1
            pos += 1
        if depth: raise ValueError('Unbalanced CREATE TABLE')
        body = statement[body_start:pos-1]
        if re.search(r'[A-Za-z_`]\w*`?\s*\.\s*`?[A-Za-z_]',body):
            raise ValueError('Cross-schema identifiers require specialist review')
        if re.search(r'\b(CHECK|GENERATED|VIRTUAL|STORED|PARTITION|TABLESPACE|SELECT|OUTFILE|INFILE|CALL)\b', body, re.I):
            raise ValueError('Advanced DDL requires specialist review')
        if re.search(r'\bDEFAULT\s*\(', body, re.I):
            raise ValueError('Expression defaults require specialist review')
        tail = statement[pos:].strip()
        if not re.fullmatch(r'ENGINE\s*=\s*InnoDB\s+(?:DEFAULT\s+)?CHARSET\s*=\s*utf8mb4(?:\s+COLLATE\s*=\s*utf8mb4_[a-z0-9_]+)?', tail, re.I):
            raise ValueError('Only InnoDB utf8mb4 tables with bounded options are supported')
        if not re.search(r'\bPRIMARY\s+KEY\b', body, re.I): raise ValueError('Primary key required')
        tables.append(table)
    if not tables or len(tables) > 64: raise ValueError('Bounded nonempty table list required')
    return tables


def migration_policy_validate(policy, migrations, commit=None):
    expected = {'schema_version', 'rules'} | ({'commit'} if commit is not None else set())
    if not isinstance(policy, dict) or set(policy) != expected or type(policy['schema_version']) is not int or policy['schema_version'] != 1:
        raise ValueError('Unsupported migration policy schema')
    if commit is not None and (not re.fullmatch('[a-f0-9]{40}', commit) or policy['commit'] != commit):
        raise ValueError('Migration policy commit mismatch')
    if not isinstance(policy['rules'], list) or len(policy['rules']) > 128: raise ValueError('Invalid migration rules')
    rules = {}
    seen_tables = set()
    for rule in policy['rules']:
        if not isinstance(rule, dict) or set(rule) != {'version','file','sha256','mode','tables'}:
            raise ValueError('Invalid migration rule fields')
        version = rule['version']
        if type(version) is not int or not MIGRATION_POLICY_BASE < version <= 1000 or version in rules:
            raise ValueError('Invalid/duplicate migration rule version')
        if rule['mode'] != 'create-empty': raise ValueError('Unsupported migration preservation mode')
        if version not in migrations: raise ValueError('Policy references missing SQL')
        name, data = migrations[version]
        if rule['file'] != name or hashlib.sha256(data).hexdigest() != rule['sha256']:
            raise ValueError('Policy SQL filename/digest mismatch')
        tables = migration_policy_sql_tables(data)
        if rule['tables'] != tables or seen_tables.intersection(tables): raise ValueError('Policy table declaration mismatch')
        seen_tables.update(tables)
        rules[version] = tables
    if set(rules) != {v for v in migrations if v > MIGRATION_POLICY_BASE}:
        raise ValueError('Every future migration requires an exact preservation rule')
    return rules


def migration_policy_for_release(release, meta, from_version):
    path = release / 'migration-policy.json'
    if not path.exists():
        if meta['schema_version'] > MIGRATION_POLICY_BASE: raise ValueError('Missing migration policy')
        return set()  # Legacy <=V21 artifacts retain all original hardcoded guards.
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MIGRATION_POLICY_LIMIT: raise ValueError('Invalid migration policy file')
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta['files'].get('migration-policy.json'):
        raise ValueError('Migration policy artifact digest mismatch')
    migrations = {}
    with zipfile.ZipFile(release/'backend.jar') as jar:
        for info in jar.infolist():
            match = re.fullmatch(r'BOOT-INF/classes/db/migration/(V(\d+)__[^/]+\.sql)', info.filename)
            if not match:
                if info.filename.startswith('BOOT-INF/classes/db/migration/') and not info.is_dir():
                    raise ValueError('Only declared versioned SQL resources are supported; Java/callback/repeatable migrations require specialist review')
                continue
            version = int(match[2])
            if version in migrations or info.file_size > 1048576: raise ValueError('Duplicate/oversize JAR migration')
            migrations[version] = (match[1], jar.read(info))
    if not migrations or max(migrations) != meta['schema_version']: raise ValueError('Policy/JAR schema mismatch')
    rules = migration_policy_validate(migration_policy_load(path.read_bytes()), migrations, meta['commit'])
    return {table for version, tables in rules.items() if from_version < version <= meta['schema_version'] for table in tables}

# END VERSIONED MIGRATION POLICY

def valid_release_id(value):return bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}',value))
def unpack(archive,dest):
 with tarfile.open(archive,'r:gz') as tar:
  members=tar.getmembers()
  if len(members)>10000 or sum(m.size for m in members)>800*1024*1024:raise ValueError('Artifact too large')
  names=set()
  for m in members:
   path=Path(m.name)
   if path.is_absolute() or '..' in path.parts or not (m.isfile() or m.isdir()) or m.name in names:raise ValueError('Unsafe archive member')
   names.add(m.name)
   if path.parts[0] not in {'backend.jar','web','release.json','migration-policy.json'}:raise ValueError('Unexpected artifact member')
  tar.extractall(dest,filter='data')
 meta=json.loads((dest/'release.json').read_text())
 if not valid_release_id(meta['id']) or not re.fullmatch('[0-9a-f]{40}',meta['commit']):raise ValueError('Invalid release metadata')
 if not isinstance(meta['schema_version'],int) or not 7<=meta['schema_version']<=1000:raise ValueError('Invalid schema version')
 actual={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file() and p!=dest/'release.json'}
 if actual!=meta['files'] or 'backend.jar' not in actual or 'web/index.html' not in actual:raise ValueError('Artifact checksum mismatch')
 with zipfile.ZipFile(dest/'backend.jar') as jar:
  versions=[int(m[1]) for name in jar.namelist() if (m:=re.search(r'/db/migration/V(\d+)__.*\.sql$',name))]
  if not versions or max(versions)!=meta['schema_version'] or 'BOOT-INF/classes/com/matrix/prp/deployment/DatabaseTool.class' not in jar.namelist():raise ValueError('Migration metadata mismatch')
 return meta
def properties(values):
 def escape(v):return str(v).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r')
 return ''.join(k+'='+escape(v)+'\n' for k,v in values.items()).encode()
def config():return yaml.safe_load(CONFIG.read_text())
def migrate(release,db,baseline=False,baseline_only=False,validate_only=False):
 runtime=release/'.migration-runtime'
 if not runtime.exists():
  runtime.mkdir()
  with zipfile.ZipFile(release/'backend.jar') as jar:
   for name in jar.namelist():
    if name.startswith('BOOT-INF/lib/') and name.endswith('.jar') or name.startswith('BOOT-INF/classes/db/migration/') and name.endswith('.sql') or name=='BOOT-INF/classes/com/matrix/prp/deployment/DatabaseTool.class':
     if '..' in Path(name).parts:raise ValueError('Unsafe JAR member')
     target=runtime/name
     target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(jar.read(name))
  for p in [runtime,*runtime.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
 cfg=config()['spring']['datasource']
 original=cfg['url']
 url=re.sub(r'(?<=/)[a-zA-Z0-9_]+(?=\?|$)',db,original,count=1)
 if '/'+db not in url:raise ValueError('Cannot select migration database')
 user=cfg['username']
 # Grant only this isolated verification schema to the existing app identity.
 if db!='matrix_prp':
  if not re.fullmatch(r'[a-zA-Z0-9_]+',user):raise ValueError('Invalid DB user')
  hosts=sql("SELECT host FROM mysql.user WHERE user='"+user+"';").splitlines()
  for host in hosts:
   if not re.fullmatch(r'[a-zA-Z0-9_.%:-]+',host):raise ValueError('Invalid DB user host')
   sql("GRANT ALL PRIVILEGES ON `"+db+"`.* TO '"+user+"'@'"+host+"';")
 values={'url':url,'user':user,'password':cfg['password'],'migrations':str(runtime/'BOOT-INF/classes/db/migration')}
 cp=str(runtime/'BOOT-INF/classes')+':'+str(runtime/'BOOT-INF/lib/*')
 actions=['validate'] if validate_only else ['baseline-v7'] if baseline_only else (['baseline-v7','migrate','validate'] if baseline else ['migrate','validate'])
 for action in actions:
  log('Database '+db+': '+action)
  run([JAVA,'-Xmx160m','-XX:MaxMetaspaceSize=128m','-cp',cp,'com.matrix.prp.deployment.DatabaseTool',action],input=properties(values),user=ACCOUNT.pw_uid,group=ACCOUNT.pw_gid,cwd=str(release))
def drop_test_db(db):
 sql('DROP DATABASE `'+db+'`;')
 user=config()['spring']['datasource']['username']
 # Remove stale per-schema grants as well as the temporary database.
 hosts=sql("SELECT Host FROM mysql.db WHERE User='"+user+"' AND Db='"+db+"';").splitlines()
 for host in hosts:sql("REVOKE ALL PRIVILEGES ON `"+db+"`.* FROM '"+user+"'@'"+host+"';")
def check_legacy(release,reference):
 migrations=release/'.migration-runtime/BOOT-INF/classes/db/migration'
 # Extract SQL only; we do not baseline or migrate the production schema here.
 with zipfile.ZipFile(release/'backend.jar') as jar:
  for name in jar.namelist():
   if re.search(r'/db/migration/V[1-7]__.*\.sql$',name):
    content=jar.read(name).decode()
    sql(content,reference)
 expected=set(sql('SHOW TABLES;',reference).splitlines())
 actual=set(sql('SHOW TABLES;').splitlines())
 assert expected==actual,'Legacy table set differs; explicit migration review required'
 for table in expected:
  def definition(db):
   return re.sub(r' AUTO_INCREMENT=\d+','',sql('SHOW CREATE TABLE `'+table+'`;',db).split('\t',1)[1])
  assert definition(reference)==definition('matrix_prp'),'Legacy schema mismatch: '+table
 log('Legacy V1-V7 schema definitions match exactly; explicit baseline is permitted')
def request(path,token=None,byte_range=None):
 headers={}
 if token:headers['Authorization']='Bearer '+token
 if byte_range:headers['Range']=byte_range
 with urllib.request.urlopen(urllib.request.Request('https://micor.top/prp'+path,headers=headers),timeout=15) as response:return response.status,response.read()
def token_for(username,user_id):
 secret=str(config()['matrix-prp']['security']['jwt-secret']).encode()
 enc=lambda value:base64.urlsafe_b64encode(value).decode().rstrip('=')
 algo='HS512' if len(secret)>=64 else 'HS384' if len(secret)>=48 else 'HS256'
 data=enc(json.dumps({'alg':algo}).encode())+'.'+enc(json.dumps({'sub':username,'uid':user_id,'iat':int(time.time()),'exp':int(time.time())+300}).encode())
 return data+'.'+enc(hmac.new(secret,data.encode(),getattr(hashlib,'sha'+algo[2:])).digest())
def check():
 for i in range(45):
  try:
   with urllib.request.urlopen('http://127.0.0.1:11000/api/health',timeout=3) as response:
    assert json.load(response)['code']=='SUCCESS'
   break
  except Exception:
   if i==44:raise
   time.sleep(2)
 for path in ['/','/learning','/notifications','/manifest.webmanifest','/sw.js']:
  status,body=request(path);assert status==200
 for row in sql('SELECT id,username FROM prp_users WHERE enabled=1 ORDER BY id LIMIT 10;').splitlines():
  user_id,username=row.split('\t');token=token_for(username,int(user_id))
  for path in ['/api/users/me','/api/dashboard/summary','/api/video/items','/api/wellness/foods/frequent','/api/practice/subjects','/api/practice/statistics']:
   status,body=request(path,token);assert status==200 and json.loads(body)['code']=='SUCCESS',path
 videos=sql('SELECT id,user_id,storage_key,size_bytes FROM prp_video_assets ORDER BY id;').splitlines()
 for row in videos:
  video,user,key,size=row.split('\t');assert (Path('/srv/matrix-prp/video/media')/user/(key+'.mp4')).stat().st_size==int(size)
 if videos:
  video,user,_,_=videos[0].split('\t');username=sql('SELECT username FROM prp_users WHERE id='+user+';')
  status,body=request('/api/video/items/'+video+'/playback',token_for(username,int(user)))
  url=json.loads(body)['data']['url'];status,body=request(url,byte_range='bytes=0-1023');assert status==206 and len(body)==1024
 log('Health, authenticated APIs, PWA and '+str(len(videos))+' private video files verified')
def point(release):
 temp=BASE/'.current-next'
 if temp.exists() or temp.is_symlink():temp.unlink()
 temp.symlink_to(release.name);os.replace(temp,BASE/'current')
def status():
 current=(BASE/'current').resolve()
 log(json.dumps({'release':current.name,'schema_version':schema_version(),'metadata':json.loads((current/'release.json').read_text()) if (current/'release.json').exists() else {},'service':subprocess.check_output(['systemctl','is-active',SERVICE]).decode().strip()}))
def deploy(allow_baseline=False):
 incoming=STATE/('incoming-'+str(int(time.time()))+'.tar.gz')
 total=0
 try:
  with incoming.open('wb') as out:
   while block:=sys.stdin.buffer.read(1024*1024):
    total+=len(block)
    if total>256*1024*1024:raise ValueError('Upload too large')
    out.write(block)
  with tempfile.TemporaryDirectory(dir=BASE,prefix='.staging-') as tmp:
   staging=Path(tmp);meta=unpack(incoming,staging)
   release=BASE/meta['id']
   previous=(BASE/'current').resolve()
   old=json.loads((previous/'release.json').read_text())
   if old.get('commit')==meta['commit']:
    log('This commit is already deployed');check();return
   if release.exists():raise ValueError('Release ID already exists')
   os.rename(staging,release)
  for p in [release,*release.rglob('*')]:
   os.chown(p,0,ACCOUNT.pw_gid);p.chmod(0o755 if p.is_dir() else 0o644)
  (release/'backend.jar').chmod(0o640)
  backend_changed=old.get('backend_source')!=meta['backend_source']
  db_before=schema_version()
  structure_before=schema_fingerprint()
  if meta['schema_version']<db_before:raise ValueError('Artifact is older than database; use reviewed rollback')
  backup=BACKUPS/meta['id'];backup.mkdir(mode=0o700)
  shutil.copytree('/etc/matrix-prp',backup/'config')
  shutil.copy2('/etc/nginx/snippets/matrix-prp.conf',backup/'nginx.conf')
  (backup/'previous.json').write_text(json.dumps({'release':previous.name,'schema_version':db_before}))
  # Only frontend changed: keep the tested running backend artifact and skip restart/migration.
  if not backend_changed:
   assert meta['schema_version']==db_before
   shutil.copy2(previous/'backend.jar',release/'backend.jar')
   meta['files']['backend.jar']=hashlib.sha256((release/'backend.jar').read_bytes()).hexdigest()
   (release/'release.json').write_text(json.dumps(meta,indent=2))
   point(release)
   try:check()
   except Exception:point(previous);raise
   log('Frontend published; backend restart and database migration skipped');return
  deploy_backend(release,previous,meta,backup)
 finally:
  if incoming.exists():incoming.unlink()

def history_fingerprint():
 # Include failed rows, checksums and ranks: version alone cannot detect partial failure.
 return hashlib.sha256(sql('SELECT * FROM flyway_schema_history ORDER BY installed_rank;').encode()).hexdigest()

def database_state():
 return {'version':schema_version(),'structure':schema_fingerprint(),'history':history_fingerprint()}

def business_fingerprint():
 # Stream a deterministic logical export; no personal records or secrets reach logs.
 command=['docker','exec','matrix-mysql','sh','-c',
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --default-character-set=utf8mb4 -uroot '
  '--single-transaction --no-tablespaces --no-create-info --skip-comments --skip-add-locks '
  '--skip-disable-keys --skip-extended-insert --order-by-primary --hex-blob --routines --events '
  '--ignore-table=matrix_prp.flyway_schema_history matrix_prp']
 digest=hashlib.sha256()
 with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as proc:
  while block:=proc.stdout.read(1024*1024):digest.update(block)
  if proc.wait()!=0:raise RuntimeError('Cannot verify database content')
 return digest.hexdigest()

def checkpoint(backup,phase,**details):
 # A full backup disk must not prevent recovery of the running application.
 try:
  path=backup/'progress.json'
  value=json.loads(path.read_text()) if path.exists() else {'started_at':time.time()}
  value.update(details);value.update(phase=phase,updated_at=time.time())
  temp=backup/'.progress.tmp';temp.write_text(json.dumps(value,indent=2));os.replace(temp,path)
 except (OSError,ValueError):log('Cannot persist deployment phase; inspect root deployment logs')
 log('Deployment phase: '+phase)

def record_result(backup,value):
 try:
  temp=backup/'.result.tmp';temp.write_text(json.dumps(value));os.replace(temp,backup/'result.json')
 except OSError:log('Cannot persist deployment result; inspect root deployment logs')

def rehearse(release,meta,backup):
 # Compare the restored snapshot with itself, never with a changing live row count.
 checkpoint(backup,'online-backup')
 if sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='matrix_prp' AND table_type='BASE TABLE' AND engine<>'InnoDB';")!='0':
  raise ValueError('Online rehearsal requires transactional InnoDB tables')
 initial=database_state()
 new_tables=migration_policy_for_release(release,meta,initial['version'])
 dump(backup/'preflight.sql')
 db='prp_verify_'+str(time.time_ns())
 sql('CREATE DATABASE `'+db+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
 try:
  checkpoint(backup,'online-rehearsal')
  restore(backup/'preflight.sql',db)
  before=snapshot(db,schema_evidence=bool(new_tables))
  migrate(release,db)
  assert_preserved(before,snapshot(db,schema_evidence=bool(new_tables)),new_empty_tables=new_tables)
  if schema_version(db)!=meta['schema_version']:raise ValueError('Rehearsal schema version mismatch')
 finally:drop_test_db(db)
 if database_state()!=initial:raise ValueError('Production schema/history changed during rehearsal')
 checkpoint(backup,'preflight-passed')
 return initial

def migrate_with_retry(release,before,content):
 # One retry only, and only if the first attempt left every verified state unchanged.
 for attempt in range(2):
  try:
   migrate(release,'matrix_prp');return
  except Exception:
   if attempt or database_state()!=before or business_fingerprint()!=content:raise
   log('Migration failed without database changes; retrying once')
   time.sleep(2)

def start_and_check(release,retry=True):
 point(release)
 try:
  run(['systemctl','start',SERVICE]);check()
 except Exception:
  if not retry:raise
  log('Application verification failed; retrying the same release once')
  run(['systemctl','restart',SERVICE]);check()

def deploy_backend(release,previous,meta,backup):
 # All expensive restoration and SQL rehearsals finish while the old app serves traffic.
 # No implicit legacy baseline is allowed here.
 try:initial=rehearse(release,meta,backup)
 except Exception:
  checkpoint(backup,'preflight-failed-production-untouched')
  raise
 new_tables=migration_policy_for_release(release,meta,initial['version'])
 pending=meta['schema_version']>initial['version']
 stopped_at=None;attempted=False;completed=False;content=None;before=None
 try:
  checkpoint(backup,'stopping',pending_migrations=pending)
  stopped_at=time.time()  # Set before stop: a failed systemctl can still have stopped Java.
  run(['systemctl','stop',SERVICE])
  before=database_state()
  if before!=initial:raise ValueError('Database changed before cutover')
  if pending:
   checkpoint(backup,'final-backup')
   dump(backup/'database.sql')
   rows=snapshot(schema_evidence=bool(new_tables));content=business_fingerprint()
   (backup/'snapshot.json').write_text(json.dumps(rows))
   checkpoint(backup,'migrating')
   attempted=True
   migrate_with_retry(release,before,content)
   assert_preserved(rows,snapshot(schema_evidence=bool(new_tables)),new_empty_tables=new_tables)
   if schema_version()!=meta['schema_version']:raise ValueError('Production schema version mismatch')
  completed=True
  checkpoint(backup,'starting')
  start_and_check(release)
  checkpoint(backup,'success',downtime_seconds=round(time.time()-stopped_at,3))
  record_result(backup,{'status':'success','commit':meta['commit'],
    'schema_version':meta['schema_version'],'time':int(time.time())})
  log('Deployment complete: '+meta['id'])
 except Exception:
  # Never restore production data automatically: new writes must not be overwritten.
  # Stop a possibly unhealthy new process before examining state or selecting an old jar.
  run(['systemctl','stop',SERVICE])
  recovery_phase='manual-review-required'
  try:
   safe=database_state()==initial
   if attempted:safe=safe and business_fingerprint()==content
   if not safe:
    checkpoint(backup,'manual-review-required',migration_completed=completed)
    raise RuntimeError('Database changed; automatic rollback blocked')
   # Flyway is enabled on this host: the old jar must validate the exact current history.
   migrate(previous,'matrix_prp',validate_only=True)
   checkpoint(backup,'restoring-application')
   start_and_check(previous)
   recovery_phase='previous-application-restored'
   checkpoint(backup,recovery_phase,downtime_seconds=round(time.time()-stopped_at,3))
  except Exception:
   run(['systemctl','stop',SERVICE])
   checkpoint(backup,'manual-review-required',migration_completed=completed)
   raise
  finally:
   record_result(backup,{'status':'failed','phase':recovery_phase})
  raise

def rollback(release_id):
 if not valid_release_id(release_id):raise ValueError('Invalid release ID')
 release=BASE/release_id
 if not release.is_dir() or release.is_symlink():raise ValueError('Unknown release')
 meta=json.loads((release/'release.json').read_text())
 if meta['schema_version']!=schema_version():raise ValueError('Cross-schema rollback requires operator review; never restore an old DB automatically')
 previous=(BASE/'current').resolve()
 run(['systemctl','stop',SERVICE]);point(release);run(['systemctl','start',SERVICE])
 try:check()
 except Exception:
  point(previous);run(['systemctl','restart',SERVICE]);raise
 log('Application rollback complete: '+release_id+'; current database and videos retained')
def baseline_only():
 # A one-time administrator operation, deliberately unavailable through SSH gateway.
 if sql("SHOW TABLES LIKE 'flyway_schema_history';"):raise ValueError('Flyway history already exists')
 archive=STATE/'baseline-artifact.tar.gz'
 with archive.open('wb') as out:
  total=0
  while block:=sys.stdin.buffer.read(1024*1024):
   total+=len(block)
   if total>256*1024*1024:raise ValueError('Upload too large')
   out.write(block)
 backup=BACKUPS/('baseline-v7-'+str(int(time.time())));backup.mkdir(mode=0o700)
 stopped=False
 try:
  with tempfile.TemporaryDirectory(dir=BASE,prefix='.baseline-') as tmp:
   release=Path(tmp);unpack(archive,release)
   release.chmod(0o755)
   for p in release.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
   run(['systemctl','stop',SERVICE]);stopped=True
   dump(backup/'database.sql');before=snapshot()
   db='prp_baseline_'+str(int(time.time()));ref=db+'_ref'
   sql('CREATE DATABASE `'+db+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
   sql('CREATE DATABASE `'+ref+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
   try:
    restore(backup/'database.sql',db);assert_preserved(before,snapshot(db))
    check_legacy(release,ref)
    migrate(release,db,baseline_only=True);assert_preserved(before,snapshot(db))
    migrate(release,'matrix_prp',baseline_only=True);assert_preserved(before,snapshot())
    assert schema_version()==7
    (backup/'result.json').write_text(json.dumps({'baseline':7,'data':'unchanged','restoration':'verified'}))
   finally:
    drop_test_db(db);sql('DROP DATABASE `'+ref+'`;')
  log('Explicit V7 baseline registered; no V1-V7 SQL replayed and no new migrations applied')
 finally:
  if stopped:run(['systemctl','start',SERVICE])
  if archive.exists():archive.unlink()
def main():
 if os.geteuid()!=0:raise SystemExit('Must run through the deployment gateway')
 if ACCOUNT is None:raise SystemExit('Runtime account openclaw is missing')
 STATE.mkdir(mode=0o700,exist_ok=True);BASE.mkdir(mode=0o755,parents=True,exist_ok=True);BACKUPS.mkdir(mode=0o700,exist_ok=True)
 with (STATE/'deploy.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  action=sys.argv[1] if len(sys.argv)>1 else ''
  if action=='deploy' and len(sys.argv)==2:deploy()
  elif action=='bootstrap-v7' and len(sys.argv)==2:baseline_only()
  elif action=='rollback' and len(sys.argv)==3:rollback(sys.argv[2])
  elif action=='status' and len(sys.argv)==2:status()
  elif action=='check' and len(sys.argv)==2:check()
  else:raise ValueError('Invalid deployment action')
if __name__=='__main__':
 try:main()
 except Exception as exc:
  # Exceptions from DB drivers can contain connection strings. Full details stay root-only.
  STATE.mkdir(mode=0o700,exist_ok=True)
  import traceback
  with (STATE/'last-error.log').open('w') as out:traceback.print_exc(file=out)
  log('Deployment failed: '+type(exc).__name__+'. Administrator details: /var/lib/matrix-prp-deploy/last-error.log')
  sys.exit(1)
