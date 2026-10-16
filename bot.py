import os
import re
from atproto import Client
import markovify
from janome.tokenizer import Tokenizer

def load_ng_words():
    ng_list = []
    # ファイルは ng_words.txt 1つに絞る！
    file_name = "ng_words.txt⁠"
    
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word and not word.startswith("#"):
                    ng_list.append(word)
                    
    print(f"Loaded {len(ng_list)} NG words.")
    return list(set(ng_list))

def is_safe(text, ng_words):
    if not text:
        return False

    clean_text = re.sub(r'https?://[\w/:%#\$&\?\(\)~\.=\+\-]+', '', text)
    clean_text = re.sub(r'@[\w\.-]+', '', clean_text).lower()
    
    if re.search(r'部$', text) or '部活' in text:
        return False

    disaster_pattern = r'(原爆|空襲|地震|震度|津波|警報|注意報|避難|災害|冠水|停電|余震)'
    if re.search(disaster_pattern, text):
        return False

    place_pattern = r'(北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄|ヒロシマ|ナガサキ|広島|長崎|沖縄県|[都道府県]|.+[市区町村])'
    if re.search(place_pattern, text):
        return False

    stripped_text = re.sub(r'[\s\.\-\_\,\/\*]', '', clean_text)
    
    leet_map = {"0": "o", "3": "e", "1": "i", "4": "a", "5": "s", "7": "t", "@": "a"}
    for leet, normal in leet_map.items():
        stripped_text = stripped_text.replace(leet, normal)
        clean_text = clean_text.replace(leet, normal)

    for word in ng_words:
        if word.isdigit() and len(word) >= 2:
            if word in stripped_text:
                return False

        if word in stripped_text:
            return False
            
        if word.isalnum() and word.isascii():
            if re.search(r'\b' + re.escape(word) + r'\b', clean_text):
                return False
        else:
            if word in clean_text:
                return False
            
    return True

def tokenize(text):
    # 日本語（ひらがな・カタカナ・漢字）が含まれる場合のみJanomeを使う
    if re.search(r'[ぁ-んァ-ヶー一-龠]', text):
        try:
            t = Tokenizer()
            return " ".join([token.surface for token in t.tokenize(text)])
        except Exception:
            return ""
    else:
        # 英語や他言語はスペースで分割する
        words = text.split()
        return " ".join(words)

def format_multilingual_spaces(sentence):
    if not sentence:
        return ""
    clean_space_text = re.sub(r'\s+', ' ', sentence).strip()
    return re.sub(r'(?<=[ぁ-んァ-ヶー一-龠])\s+(?=[ぁ-んァ-ヶー一-龠a-zA-Z])|(?<=[a-zA-Zぁ-んァ-ヶー一-龠])\s+(?=[ぁ-んァ-ヶー一-龠])', '', clean_space_text)

def main():
    client = Client()
    client.login(os.environ['BSKY_HANDLE'], os.environ['BSKY_PASSWORD'])
    ng_words = load_ng_words()

    # Discoverフィードを取得
    target_feed = 'at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot'
    
    japanese_posts = []
    english_posts = []
    other_posts = []
    
    cursor = None
    # 均等に集めるために少し多めに巡回
    for _ in range(8):
        try:
            params = {'feed': target_feed, 'limit': 50}
            if cursor:
                params['cursor'] = cursor
            response = client.app.bsky.feed.get_feed(params)
            if not response or not response.feed:
                break
            
            for item in response.feed:
                if hasattr(item.post.record, 'text'):
                    text = item.post.record.text
                    if is_safe(text, ng_words) and len(text) >= 2:
                        tokenized = tokenize(text)
                        
                        # 言語ごとに分類して、各上限（例: 15件まで）均等にストックする
                        if re.search(r'[ぁ-んァ-ヶー一-龠]', text):
                            if len(japanese_posts) < 15:
                                japanese_posts.append(tokenized)
                        elif re.search(r'[a-zA-Z]', text):
                            if len(english_posts) < 15:
                                english_posts.append(tokenized)
                        else:
                            if len(other_posts) < 15:
                                other_posts.append(tokenized)

            cursor = getattr(response, 'cursor', None)
            if not cursor:
                break
        except Exception as e:
            print(f"Error: {e}")
            break

    # 各言語からバランスよく集まった素材を合体する
    cleaned_texts = japanese_posts + english_posts + other_posts
    print(f"Collected - JP: {len(japanese_posts)}, EN: {len(english_posts)}, Others: {len(other_posts)}")

    if len(cleaned_texts) < 2:
        print("Not enough source material!")
        return

    source_data = "\n".join(cleaned_texts)
    text_model = markovify.NewlineText(source_data, state_size=1)

    # ポスト生成
    for _ in range(10): 
        sentence = text_model.make_short_sentence(40, tries=100)
        if sentence:
            final_post = format_multilingual_spaces(sentence)
            if is_safe(final_post, ng_words):
                if "#" not in final_post and "＃" not in final_post:
                    client.send_post(text=final_post)
                    print(f"Posted: {final_post}")
                    break

if __name__ == "__main__":
    main()
