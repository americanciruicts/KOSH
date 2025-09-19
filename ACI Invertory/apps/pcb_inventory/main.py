#Import Necessary Libraries
from tkinter import *
import tkinter as tk 
from tkinter import ttk
import pyodbc

#Set function for focus next primarily used by tab
def focus_next_widget(event):
    event.widget.tk_focusNext().focus()
    return("break")

#Retrieve Job# from input
def retrieveJob():
    global pcnJob
    pcnJob = varJob.get("1.0",'end-1c')
    return pcnJob

#Retrieve Qty from input
def retrieveQty():
    global pcnQty
    pcnQty = varQty.get("1.0",'end-1c')
    return pcnQty

#Retrieve Location from input
def retrieveLoc():
    global pcnLoc
    pcnLoc = varLoc.get()
    return pcnLoc

#Retrieve PCB Type from input
def retrievePcbType():
    global pcnPcbType
    pcnPcbType = varPcbType.get()
    return pcnPcbType

#Access Driver Connection
def get_dbconn(file, password=None):
    pyodbc.pooling = False
    driver = '{Microsoft Access Driver (*.mdb, *.accdb)}'
    dbdsn = f'Driver={driver};Dbq={file};'
    if password:
        dbdsn += f'Pwd={password};'
    return pyodbc.connect(dbdsn)

#Define function for finding old quantity
def findOldQty():
    #Set File Location and Table Name
    dbconn = get_dbconn(r'Y:\\Inventory\\INVENTORY TABLE.mdb')
    cursor = dbconn.cursor()
    tablename = 'tblPCB_Inventory'
    #Select from Job and PCB Type
    sql = f"select * from [{tablename}] where (job = '"+retrieveJob()+"' and pcb_type= '"+retrievePcbType()+"');"
    cursor.execute(sql)
    #Find Quantity from Database
    for row in cursor.fetchall():
        oldQty = int(row.Qty)
    try:
        return oldQty
    except:
        return None

#Define a Function that Stocks Inventory even if not in the database.
def stockPCB():
    #Check for blank fields in form
    if retrieveJob() == "" or retrieveLoc() == "" or str(retrievePcbType()) == "0" or retrieveQty() == "":
        checkFields()
        return
    #Find Old Quantity
    oldQty = findOldQty()
    #Set Table Properties
    dbconn = get_dbconn(r'Y:\\Inventory\\INVENTORY TABLE.mdb')
    cursor = dbconn.cursor()
    tablename = 'tblPCB_Inventory'
    #Create new entry if no entry found
    if oldQty == None:
        sql = f"insert into [{tablename}](job, pcb_type, qty, location) values ('"+retrieveJob()+"','"+retrievePcbType()+"',"+retrieveQty()+",'"+retrieveLoc()+"');"
        cursor.execute(sql)
        cursor.commit()
        stockComplete(retrieveQty())
    #If entry found update quantity
    else:
        newQty = oldQty + int(retrieveQty())
        sql = f"update [{tablename}] set qty = "+str(newQty)+" where (job = '"+retrieveJob()+"' and pcb_type = '"+retrievePcbType()+"');"
        cursor = dbconn.cursor()
        cursor.execute(sql)
        cursor.commit()
        stockComplete(newQty)


#Define a Function that Pulls from Quantity or Errors if There's Not Enough in Inventory
def pickPCB():
    #Check for blank fields in form
    if retrieveJob() == "" or retrieveLoc() == "" or retrievePcbType == "" or retrieveQty() == "":
        checkFields()
        return
    #Find Old Quantity
    oldQty = findOldQty()
    #Set Table Properties
    dbconn = get_dbconn(r'Y:\\Inventory\\INVENTORY TABLE.mdb')
    cursor = dbconn.cursor()
    tablename = 'tblPCB_Inventory'
    #Calculate New Quantity if job found
    if oldQty == None:
        wrongJob()
        return
    else:
        newQty = oldQty - int(retrieveQty())
    #Check if There is Enough In Stock
    if newQty < 0:
        lowQuantity()
    #If Enough in Stock Pull it from Inventory Database
    else:
        sql = f"update [{tablename}] set qty = "+str(newQty)+" where (job = '"+retrieveJob()+"' and pcb_type = '"+retrievePcbType()+"');"
        cursor = dbconn.cursor()
        cursor.execute(sql)
        cursor.commit()
        pickComplete()

#Define event for close window
def closeNewWindow(event):
    newWindow.destroy()
    app.focus_set()
    varJob.focus_set()

#Define error message for low quantity
def lowQuantity():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Low Quantity")
    newWindow.geometry("400x200")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    oldQty = findOldQty()
    Label(newWindow, text = "Inventory has only "+str(oldQty)+",\n pick "+str(oldQty)+" or less.",font=("Arial bold", 24) ,fg="red").pack()
    newWindow.bind("<Return>",closeNewWindow)

#Define error screen for wrong/not listed Job number
def wrongJob():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Wrong Job")
    newWindow.geometry("400x200")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    Label(newWindow, text = retrieveJob()+" not found.\nPlease double check\njob number.",font=("Arial bold", 24) ,fg="red").pack()
    newWindow.bind("<Return>",closeNewWindow)

#Define screen for correct pick job
def pickComplete():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Pick Completed")
    newWindow.geometry("400x200")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    oldQty = findOldQty()
    Label(newWindow, text = retrieveQty()+" Picked.\n"+str(oldQty)+" left in inventory.",font=("Arial bold", 24) ,fg="green").pack()
    varJob.delete('1.0',END)
    varQty.delete('1.0',END)
    varLoc.set('')
    varPcbType.set(None)
    newWindow.bind("<Return>",closeNewWindow)

#Define screen for correct pick job
def checkFields():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Check Fields")
    newWindow.geometry("400x200")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    Label(newWindow, text = "Please fill out ALL\nfields.",font=("Arial bold", 24) ,fg="red").pack()
    newWindow.bind("<Return>",closeNewWindow)

#Define screen for correct pick job
def stockComplete(newQty):
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Stock Completed")
    newWindow.geometry("400x200")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    Label(newWindow, text = retrieveQty()+" Stocked.\n"+str(newQty)+" in inventory.",font=("Arial bold", 24) ,fg="green").pack()
    varJob.delete('1.0',END)
    varQty.delete('1.0',END)
    varLoc.set('')
    varPcbType.set(None)
    newWindow.bind("<Return>",closeNewWindow)

#Setup UI
def pcbOptions():
    #Setup Frame border label.
    framePcbSelect = LabelFrame(app, text="Stock and Pick PCB",padx=3,pady=5)
    framePcbSelect.grid(row=0,column=0,sticky='NW',columnspan=6,padx='5',pady='5')
    #Set Job# Label and Textbox
    Label(framePcbSelect,text="Job #").grid(row=0,column=0,padx=6,pady=3,sticky='W')
    global varJob
    varJob = Text(framePcbSelect,height=1,width=9)
    varJob.grid(row=0,column=1,columnspan=1,padx=6,pady=3,sticky='W')
    varJob.bind("<Tab>", focus_next_widget)
    #Set Quantity Label and Textbox
    Label(framePcbSelect,text="Quantity").grid(row=1,column=0,padx=6,pady=3,sticky='W')
    global varQty
    varQty = Text(framePcbSelect,height=1,width=9)
    varQty.grid(row=1,column=1,columnspan=1,padx=6,pady=3,sticky='W')
    varQty.bind("<Tab>", focus_next_widget)
    #Set Location Label and Combo Box
    Label(framePcbSelect,text="Location").grid(row=1,column=2,padx=6,pady=3,sticky='W')
    global varLoc
    n = tk.StringVar(framePcbSelect)
    varLoc = ttk.Combobox(framePcbSelect, width = 27, textvariable = n)
    varLoc['values'] = (
        "1000-1999",
        "2000-2999",
        "3000-3999",
        "4000-4999",
        "5000-5999",
        "6000-6999",
        "7000-7999",
        "8000-8999",
        "9000-9999",
        "10000-10999"
    )
    varLoc.grid(row=1,column=3,columnspan=3,padx=6,pady=3,sticky='W')
    varLoc.current(7)
    #Set PCB Type Radio Buttons
    global varPcbType
    varPcbType = StringVar(framePcbSelect, value=0)
    Radiobutton(framePcbSelect,text="Bare PCB",variable=varPcbType,value="Bare",command=retrievePcbType,width='15',anchor='w').grid(row=2,column=0,padx=6,pady=3,sticky='W',columnspan=2)
    Radiobutton(framePcbSelect,text="Partial Assembly",variable=varPcbType,value="Partial",command=retrievePcbType,width='15',anchor='w').grid(row=3,column=0,padx=6,pady=3,sticky='W',columnspan=2)
    Radiobutton(framePcbSelect,text="Completed Assembly",variable=varPcbType,value="Completed",command=retrievePcbType,width='15',anchor='w').grid(row=4,column=0,padx=6,pady=3,sticky='W',columnspan=2)
    Radiobutton(framePcbSelect,text="Ready to Ship",variable=varPcbType,value="Ready to Ship",command=retrievePcbType,width='15',anchor='w').grid(row=5,column=0,padx=6,pady=3,sticky='W',columnspan=2)
    #Set Buttons for Stock and Pick
    Button(app, text = "Stock", command = lambda : safetyCheckStock(),width='28',height='7', bg= "#6fbffb").grid(row=6,column=0,padx='4',pady='4',sticky='W')
    Button(app, text = "Pick", command = lambda : safetyCheckPick(),width='28',height='7', bg="#959799").grid(row=6,column=1,padx='3',pady='4',sticky='W')

#Define function for popup to check if user input is to be continued on pick
def safetyCheckPick():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Safety Check")
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    newWindow.focus_set()
    oldQty = findOldQty()
    Label(newWindow, text = "Are you sure you want\nto pick "+retrieveQty()+" of Job "+retrieveJob()+"?",font=("Arial bold", 24) ,fg="black").grid(row=0,column=0,padx=30,pady=3,sticky='W',columnspan=2)
    Button(newWindow, text = "Yes", command = lambda : safetyDecisionPick(True),width='28',height='7', bg= "#6fbffb").grid(row=1,column=0,padx='4',pady='4',sticky='W')
    Button(newWindow, text = "No", command = lambda : safetyDecisionPick(False),width='28',height='7', bg="#959799").grid(row=1,column=1,padx='4',pady='4',sticky='W')
    newWindow.bind("<Return>",closeNewWindow)

#Run pick PCB if input was yes.
def safetyDecisionPick(decision):
    newWindow.destroy()
    if decision:
        pickPCB()

#Define function for popup to check if user input is to be continued on stock
def safetyCheckStock():
    global newWindow
    newWindow = Toplevel()
    newWindow.title("Safety Check")
    newWindow.focus_set()
    icon =PhotoImage(file='logo.png')
    newWindow.iconphoto(False, icon)
    oldQty = findOldQty()
    Label(newWindow, text = "Are you sure you want\nto stock "+retrieveQty()+" of Job "+retrieveJob()+"?",font=("Arial bold", 24) ,fg="black").grid(row=0,column=0,padx=30,pady=3,sticky='W',columnspan=2)
    Button(newWindow, text = "Yes", command = lambda : safetyDecisionStock(True),width='28',height='7', bg= "#6fbffb").grid(row=1,column=0,padx='4',pady='4',sticky='W')
    Button(newWindow, text = "No", command = lambda : safetyDecisionStock(False),width='28',height='7', bg="#959799").grid(row=1,column=1,padx='4',pady='4',sticky='W')
    newWindow.bind("<Return>",closeNewWindow)

#Run stock PCB if input was yes.
def safetyDecisionStock(decision):
    newWindow.destroy()
    if decision:
        stockPCB()

#Set Window Options and Launch
app = Tk()
app.title("PCB Stock and Pick")
app.geometry("432x350")
icon =PhotoImage(file='logo.png')
app.iconphoto(False, icon)
pcbOptions()
varJob.focus_set()
app.mainloop()