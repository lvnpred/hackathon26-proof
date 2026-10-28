"""Ordinary English and Hinglish words heard in an OPD dictation (plan I1-g simple, Task 1). Pure data, stdlib only.

correct_drugs never rewrites one of these words, and the lexicon import refuses a brand that is one or holds one.
"""
_EN = """
a about above after afternoon again against age ago all also always am an and any are around as at away back bad bath be because bed bedtime
been before being below best better between big blood body both bowel boy breakfast breath breathing burning but by call came can cannot care
case cause check chest child cold come comes complaint condition continue cough could daily day days dead diet different dinner do does done
dose down drink drinking dry during each ear early eat eating eight eighteen eleven else empty end evening every exercise eye eyes face fall
family fast fever few fifteen fifty find fine first five follow followed following food foot for forty four fourteen free from full gave get
give given glass go going good great had half hand has have he head health hear heart heavy help her here high him his history home hot hour
hours how if ill in inside into is it its itch itching joint just keep kept kind knee know last later leave left leg less level life light like
little liver long look loose low lower lunch made make man many may me meal meals medicine medicines might milk minutes month months more
morning most mother much must my name near neck need needed never new next night nine nineteen no normal nose not nothing now number of off
old on once one only open or other our out over pain patient people per period pills plan please plenty point pressure problem put rash rest
review right said same say second see seen seven seventeen severe she should side since sir six sixteen skin sleep slight small so some
something sometimes soon sore spoon start started stay still stomach stop stool stools such sugar swelling syrup tablet tablets take taken
taking tell ten test tests than thank that the their them then there these they thing think third thirteen thirty this those three thrice
throat through time times tired to today together told tomorrow too took total twelve twenty twice two under until up upper urine us use used
very vomiting walk want warm was water we week weekly weeks weight well went were what when where which while white who why will with within
without woman work worse would year years yes yesterday you young your after-food before-food
advise advised advice allergy allergic anxiety appetite attack avoid bleeding block blurred calm chills clear constipation cramps cream
diarrhoea diarrhea dizziness drops drowsy duration fasting feeling fluid fluids gargle giddiness headache hungry infection injection inhaler
intake lotion mild motion nausea nasal ointment oral powder regular relief reduce repeat routine salt sachet sharp shower sneezing spicy steam
strength sweating tablespoon teaspoon tender vitamin weakness wound abdomen abdominal ankle arm belly bone bones brain breast cheek elbow finger
fingers gums hip hips jaw kidney kidneys knees lips lung lungs mouth muscle muscles nail nails palm shoulder spine teeth thigh thumb toe toes
tongue tooth waist wrist monday tuesday wednesday thursday friday saturday sunday january february march april june july august september
october november december
"""
_HI = """
aap aaj abhi accha acha aur baad baar bahut band bas bhi bukhar bukhaar chai chalo chaliye chawal chini dawa dawai dard dekho din dhoop doodh
dono ek fir garam goli haan hai hain halka hum kal kam kar karo karna khana khane khao khaana khansi khujli kya lekin lo mat matlab mein mai
nahi neend nimbu paani pani pehle pet phir raat roz roti sab sar sardi saans shaam subah suji tab teen thanda theek thik tum ulti wala wali yeh
zukam zyada jaldi dhire aadha pura chamach pehle-khana khane-ke-baad
"""
WORDS = frozenset((_EN + _HI).split())
