"""Original vector-like chess artwork, explicit contrast, two native layouts."""
from functools import lru_cache
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import chess

BG='#101e2c';PANEL='#1a2d3e';EDGE='#375065';WHITE='#fff9ec';MUTED='#b6c9cf';MINT='#84edbd';ORANGE='#ffac70';RED='#ff8486';LIGHT='#efe4ce';DARK='#557582'
FONT='/System/Library/Fonts/Avenir Next.ttc'
MONO='/System/Library/Fonts/Menlo.ttc'

@lru_cache(maxsize=128)
def font(size,bold=False,mono=False):
    return ImageFont.truetype(MONO if mono else FONT,int(size),index=0 if (bold or mono) else 5)

def text(draw,xy,content,size=40,color=WHITE,bold=False,anchor=None,mono=False):
    draw.text(xy,str(content),font=font(size,bold,mono),fill=color,anchor=anchor,stroke_width=0)

def measure(content,size=40,bold=False):return font(size,bold).getlength(str(content))

def wrap(content,width,size=40,bold=False):
    lines=[];line=''
    for word in str(content).split():
        candidate=(line+' '+word).strip()
        if line and measure(candidate,size,bold)>width:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines

def paragraph(draw,xy,content,width,size=40,color=WHITE,bold=False,leading=1.3,maxlines=None):
    lines=wrap(content,width,size,bold)
    if maxlines and len(lines)>maxlines:raise ValueError(f'Text exceeds {maxlines} lines: {content}')
    for i,line in enumerate(lines):text(draw,(xy[0],xy[1]+i*size*leading),line,size,color,bold)
    return len(lines)*size*leading

def rr(draw,box,fill=PANEL,radius=20,outline=None,width=2):draw.rounded_rectangle(tuple(map(round,box)),radius=radius,fill=fill,outline=outline,width=width)

def ease(v):v=max(0,min(1,v));return v*v*(3-2*v)

class Layout:
    def __init__(self,portrait=False):
        self.portrait=portrait;self.w,self.h=(1080,1920) if portrait else (1920,1080)
        self.bx,self.by,self.bs=(86,346,816) if portrait else (86,192,712)
        self.px,self.py,self.pw=(86,1240,816) if portrait else (968,228,830)
        self.caption_y=1590 if portrait else 942
        self.title_y=156 if portrait else 84
        self.title_size=66 if portrait else 68
    def square(self,sq):
        x=chess.square_file(sq);y=7-chess.square_rank(sq);s=self.bs/8
        return self.bx+x*s+s/2,self.by+y*s+s/2

@lru_cache(maxsize=32)
def background(portrait):
    L=Layout(portrait);im=Image.new('RGB',(L.w,L.h),BG);d=ImageDraw.Draw(im)
    # Quiet geometric chessboard echoes; nothing competes with the main board.
    for i in range(10):
        col=(18+i//3,33+i//2,47+i//2)
        d.line([(0,L.h*.16+i*86),(L.w,L.h*.16+i*86-160)],fill=col,width=1)
    d.line([(64,124 if portrait else 63),(L.w-(150 if portrait else 64),124 if portrait else 63)],fill=EDGE,width=2)
    text(d,(86,73 if portrait else 20),'GPT LEARNING',28,MINT,True)
    text(d,(L.w-(178 if portrait else 84),73 if portrait else 20),'02 / CHESS',25,MUTED,True,anchor='ra')
    # Raised board frame, drawn consistently in both compositions.
    rr(d,(L.bx-26,L.by-26,L.bx+L.bs+26,L.by+L.bs+26),'#253d4d',24,EDGE,2)
    return im

@lru_cache(maxsize=128)
def piece_sprite(symbol,size):
    # All silhouettes are original procedural drawings. No font glyphs or third-party sprites.
    S=4;n=100;im=Image.new('RGBA',(n*S,n*S));d=ImageDraw.Draw(im)
    white=symbol.isupper();fill=WHITE if white else '#122435';edge='#142737' if white else '#d8edf0';detail='#425763' if white else '#a5c5d3'
    def points(ps):return [(round(x*S),round(y*S)) for x,y in ps]
    def poly(ps,f=fill):d.polygon(points(ps),fill=f);d.line(points(ps+[ps[0]]),fill=edge,width=2*S,joint='curve')
    def ellipse(box,f=fill):d.ellipse(tuple(round(x*S) for x in box),fill=f,outline=edge,width=2*S)
    def line(ps,c=detail,w=2):d.line(points(ps),fill=c,width=w*S,joint='curve')
    def box(b):d.rounded_rectangle(tuple(round(x*S) for x in b),radius=2*S,fill=fill,outline=edge,width=2*S)
    # Subtle grounding shadow is visible on both square colors.
    d.ellipse((18*S,88*S,83*S,98*S),fill=(4,12,20,70))
    kind=symbol.lower()
    if kind=='p':
        poly([(43,40),(57,40),(60,62),(69,78),(31,78),(40,62)])
        ellipse((35,15,65,45));box((32,72,68,81))
    elif kind=='r':
        poly([(28,44),(72,44),(65,76),(35,76)])
        poly([(23,18),(35,18),(35,29),(44,29),(44,18),(56,18),(56,29),(65,29),(65,18),(77,18),(77,46),(23,46)])
        line([(29,51),(71,51)])
    elif kind=='n':
        poly([(29,76),(34,61),(50,47),(35,52),(24,48),(22,36),(38,22),(39,10),(49,17),(60,12),(70,28),(76,52),(68,76)])
        line([(59,26),(67,42),(66,63)],detail,3)
        ellipse((39,29,44,34),edge)
        line([(24,43),(35,43)])
    elif kind=='b':
        poly([(43,46),(57,46),(59,62),(70,77),(30,77),(41,62)])
        poly([(50,9),(65,29),(66,40),(57,51),(43,51),(34,40),(35,29)])
        line([(54,22),(44,39)],edge,3);ellipse((46,5,54,13))
    elif kind=='q':
        poly([(31,40),(69,40),(64,61),(69,77),(31,77),(36,61)])
        poly([(24,26),(37,39),(40,18),(50,36),(61,18),(64,39),(77,26),(69,54),(31,54)])
        for x,y in [(23,24),(39,16),(61,16),(77,24)]:ellipse((x-4,y-4,x+4,y+4))
        line([(35,59),(65,59)],detail,3)
    elif kind=='k':
        poly([(29,36),(38,31),(50,35),(62,31),(71,36),(65,57),(63,65),(71,77),(29,77),(37,65),(35,57)])
        poly([(46,8),(54,8),(54,17),(63,17),(63,25),(54,25),(54,37),(46,37),(46,25),(37,25),(37,17),(46,17)])
        line([(37,58),(63,58)],detail,3)
    box((27,75,73,85));box((21,84,79,94))
    return im.resize((int(size),int(size)),Image.Resampling.LANCZOS)

def arrow(im,start,end,color=MINT,width=13,progress=1):
    if progress<=0:return
    sx,sy=start;ex,ey=end;ex=sx+(ex-sx)*ease(progress);ey=sy+(ey-sy)*ease(progress)
    dx=ex-sx;dy=ey-sy;length=math.hypot(dx,dy)
    if length<3:return
    ux,uy=dx/length,dy/length;head=width*2.4
    d=ImageDraw.Draw(im);d.line([(sx,sy),(ex-ux*head*.6,ey-uy*head*.6)],fill=color,width=width)
    d.polygon([(ex,ey),(ex-ux*head-uy*head*.58,ey-uy*head+ux*head*.58),(ex-ux*head+uy*head*.58,ey-uy*head-ux*head*.58)],fill=color)

def board(im,L,fen,move=None,progress=1,highlights=(),arrows=(),check=True):
    b=chess.Board(fen);d=ImageDraw.Draw(im);s=L.bs/8
    for rank in range(8):
        for file in range(8):
            sq=chess.square(file,rank);x=L.bx+file*s;y=L.by+(7-rank)*s
            d.rectangle((round(x),round(y),round(x+s),round(y+s)),fill=LIGHT if (rank+file)%2 else DARK)
    mv=chess.Move.from_uci(move) if move else None
    if mv and mv not in b.legal_moves:raise ValueError(f'Illegal animated move {move} at {fen}')
    for sq,color in highlights:
        if isinstance(sq,str):sq=chess.parse_square(sq)
        x,y=L.square(sq);d.rectangle((x-s/2+4,y-s/2+4,x+s/2-4,y+s/2-4),outline=color,width=6)
    if mv:
        for sq in [mv.from_square,mv.to_square]:
            x,y=L.square(sq);d.rectangle((x-s/2+2,y-s/2+2,x+s/2-2,y+s/2-2),outline=ORANGE,width=5)
    moving=[];pieces=b.piece_map();p=max(0,min(1,progress))
    if mv:
        moving.append((pieces.pop(mv.from_square),mv.from_square,mv.to_square,mv.promotion))
        if p>.75:pieces.pop(mv.to_square,None)
        if b.is_en_passant(mv) and p>.75:pieces.pop(mv.to_square+(-8 if b.turn else 8),None)
        if b.is_castling(mv):
            rf=chess.square(7 if chess.square_file(mv.to_square)==6 else 0,chess.square_rank(mv.from_square))
            rt=chess.square(5 if chess.square_file(mv.to_square)==6 else 3,chess.square_rank(mv.from_square))
            moving.append((pieces.pop(rf),rf,rt,None))
    size=round(s*.92)
    for sq,piece in pieces.items():
        x,y=L.square(sq);im.paste(piece_sprite(piece.symbol(),size),(round(x-size/2),round(y-size/2)),piece_sprite(piece.symbol(),size))
    for piece,frm,to,promotion in moving:
        x0,y0=L.square(frm);x1,y1=L.square(to);q=ease(p)
        x=x0+(x1-x0)*q;y=y0+(y1-y0)*q-math.sin(q*math.pi)*s*.10
        if promotion and p>.9:piece=chess.Piece(promotion,piece.color)
        spr=piece_sprite(piece.symbol(),size);im.paste(spr,(round(x-size/2),round(y-size/2)),spr)
    # Coordinates have their own dark frame, not variable square backgrounds.
    d=ImageDraw.Draw(im)
    for i in range(8):
        text(d,(L.bx+(i+.5)*s,L.by+L.bs+9),'abcdefgh'[i],20,MUTED,True,anchor='mt')
        text(d,(L.bx-12,L.by+(i+.5)*s),str(8-i),20,MUTED,True,anchor='mm')
    if check:
        shown=b.copy()
        if mv and p>=1:shown.push(mv)
        if shown.is_check():
            king=shown.king(shown.turn);x,y=L.square(king)
            d.rounded_rectangle((x-s/2+3,y-s/2+3,x+s/2-3,y+s/2-3),radius=12,outline=RED,width=6)
    for a in arrows:
        frm,to,*rest=a;arrow(im,L.square(chess.parse_square(frm)),L.square(chess.parse_square(to)),rest[0] if rest else MINT,progress=rest[1] if len(rest)>1 else 1)

def badge(d,x,y,label,color=MINT,size=25):
    width=measure(label,size,True)+32;rr(d,(x,y,x+width,y+size+18),PANEL,10,color,2);text(d,(x+16,y+5),label,size,color,True)

def avatar(im,x,y,size=150,t=0,speaking=False,engine=False,dark=False):
    d=ImageDraw.Draw(im);rr(d,(x,y,x+size,y+size),LIGHT if (engine or dark) else PANEL,round(size*.2),EDGE,2)
    spr=piece_sprite('n' if engine else ('k' if dark else 'K'),round(size*.82));im.paste(spr,(round(x+size*.09),round(y+size*.06)),spr)
    # Small expressive eyes turn an original king silhouette into our presenter.
    if not engine:
        ey=y+size*.53;blink=1 if int(t*10)%47 else .18
        for ex in (x+size*.44,x+size*.56):d.ellipse((ex-3,ey-4*blink,ex+3,ey+4*blink),fill=WHITE if dark else BG)
        mouth=2+(abs(math.sin(t*18))*6 if speaking else 0)
        d.ellipse((x+size*.47,y+size*.60,x+size*.54,y+size*.60+mouth),fill=WHITE if dark else BG)


def captions(im,L,lines):
    if not lines:return
    d=ImageDraw.Draw(im);size=43 if L.portrait else 38
    if len(lines)>2:raise ValueError('More than two caption lines')
    widest=max(measure(s,size,True) for s in lines)
    cx=(L.w-96)/2 if L.portrait else L.w/2
    h=len(lines)*size*1.3+25;y=L.caption_y
    rr(d,(cx-widest/2-23,y,cx+widest/2+23,y+h),'#07121d',16,'#4b6676',2)
    for i,line in enumerate(lines):text(d,(cx,y+10+i*size*1.3),line,size,WHITE,True,anchor='mt')
